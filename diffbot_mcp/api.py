"""Token resolution and the shared HTTP helper behind every Diffbot API call."""

import asyncio
import json
import os
import pathlib
from typing import Any, Optional

import aiohttp
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token, get_http_request

# DIFFBOT_TOKEN is this server's historical name; DIFFBOT_API_TOKEN and the credentials
# file are what the db CLI and diffbot-skills read, so one credential serves both.
TOKEN_ENV_VARS = ("DIFFBOT_TOKEN", "DIFFBOT_API_TOKEN")
CREDENTIALS_PATH = pathlib.Path.home() / ".diffbot" / "credentials"
CREDENTIALS_KEY = "DIFFBOT_API_TOKEN"

REQUEST_TIMEOUT_SECONDS = 120

MISSING_TOKEN = (
    "No Diffbot token found. On the HTTP transport pass it as 'Authorization: Bearer <token>' "
    "or '?token=<token>'; otherwise set DIFFBOT_TOKEN or DIFFBOT_API_TOKEN in the environment, "
    f"or write '{CREDENTIALS_KEY}=<token>' to {CREDENTIALS_PATH}. "
    "Get a free token at https://app.diffbot.com/get-started"
)


def _credentials_file_token() -> str:
    try:
        lines = CREDENTIALS_PATH.read_text().splitlines()
    except OSError:
        return ""
    for line in lines:
        line = line.strip()
        if line.startswith(f"{CREDENTIALS_KEY}="):
            return line.split("=", 1)[1].strip().strip("'\"")
    return ""


def resolve_token() -> str:
    """Per-request credentials first, then the environment, then the credentials file."""
    try:
        request = get_http_request()
    except RuntimeError:
        request = None  # stdio transport: no request in flight

    if request is not None:
        # Set when OAuth is on: the verified token resolves to the user's Diffbot API token
        access_token = get_access_token()
        if access_token is not None and access_token.claims.get("diffbot_token"):
            return access_token.claims["diffbot_token"]
        auth_header = request.headers.get("Authorization", "")
        if auth_header.lower().startswith("bearer "):
            return auth_header[7:].strip()
        token = request.query_params.get("token")
        if token:
            return token

    for var in TOKEN_ENV_VARS:
        token = os.getenv(var, "").strip()
        if token:
            return token

    token = _credentials_file_token()
    if token:
        return token

    raise ToolError(MISSING_TOKEN)


async def _error_message(response: aiohttp.ClientResponse) -> str:
    body = await response.text()
    message: Optional[str] = None
    try:
        data = json.loads(body)
        if isinstance(data, dict):
            message = data.get("message") or data.get("error")
    except ValueError:
        pass

    if response.status in (401, 403):
        return "Invalid or unauthorized Diffbot token" + (f": {message}" if message else "")
    if response.status == 429:
        retry_after = response.headers.get("Retry-After")
        return "Diffbot rate limit exceeded" + (f", retry after {retry_after}s" if retry_after else "")
    if not message:
        message = body[:200] + ("..." if len(body) > 200 else "")
    return f"Diffbot API error {response.status}: {message}"


def clean_params(params: dict) -> dict:
    """Drop None values and render booleans as the 1/0 the Diffbot APIs expect."""
    cleaned = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, bool):
            value = 1 if value else 0
        cleaned[key] = value
    return cleaned


async def request(
    url: str,
    *,
    params: Optional[dict] = None,
    json_body: Any = None,
    headers: Optional[dict] = None,
    as_text: bool = False,
    method: str = "GET",
) -> Any:
    """One Diffbot API call. Non-2xx responses become a ToolError carrying the API's own message."""
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(
                method, url, params=clean_params(params or {}), json=json_body, headers=headers
            ) as response:
                if response.status >= 400:
                    raise ToolError(await _error_message(response))
                if as_text:
                    return await response.text()
                return await response.json(content_type=None)
    except asyncio.TimeoutError:
        raise ToolError(f"Diffbot request timed out after {REQUEST_TIMEOUT_SECONDS}s: {url}")
    except aiohttp.ClientError as error:
        raise ToolError(f"Diffbot request failed: {error}")
