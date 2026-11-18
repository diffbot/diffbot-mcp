"""Token resolution and the diffbot SDK client behind every Diffbot API call."""

import os
import pathlib
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

import httpx
from diffbot import AuthError, DiffbotAsync, DiffbotError, RateLimitError
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


def tool_error(error: Exception) -> ToolError:
    """Turn an SDK or transport failure into a ToolError carrying the API's own message."""
    if isinstance(error, ToolError):
        return error
    if isinstance(error, AuthError):
        return ToolError("Invalid or unauthorized Diffbot token" + (f": {error.message}" if error.message else ""))
    if isinstance(error, RateLimitError):
        return ToolError("Diffbot rate limit exceeded" + (f", retry after {error.retry_after}s" if error.retry_after else ""))
    if isinstance(error, (DiffbotError, ValueError)):  # APIError, JobError, ValidationError; ValueError: a non-JSON body
        return ToolError(str(error))
    if isinstance(error, httpx.TimeoutException):
        return ToolError(f"Diffbot request timed out after {REQUEST_TIMEOUT_SECONDS}s")
    if isinstance(error, httpx.HTTPError):
        return ToolError(f"Diffbot request failed: {error}")
    raise error


@asynccontextmanager
async def diffbot(token: Optional[str] = None, *, retry: Optional[bool] = None) -> AsyncIterator[DiffbotAsync]:
    """A diffbot SDK client for one tool call, authenticated with the caller's token.

    A client per call because the token is per request on the HTTP transport. SDK errors
    raised inside the block leave it as ToolErrors. ``retry=False`` turns off the SDK's
    retries (for calls that are not idempotent); ``None`` keeps its default policy.
    """
    try:
        async with DiffbotAsync(token or resolve_token(), timeout=REQUEST_TIMEOUT_SECONDS, retry=retry) as client:
            yield client
    except (DiffbotError, ValueError, httpx.HTTPError) as error:
        raise tool_error(error) from error
