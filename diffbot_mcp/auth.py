"""OAuth via the Diffbot dashboard, enabled when DIFFBOT_OAUTH_ISSUER is set.

The dashboard issues dbat_-prefixed access tokens and introspects them for this server,
answering with the user's own Diffbot API token. Any other bearer token is a static
Diffbot API token and passes through for the Diffbot APIs to validate, as before OAuth.
"""

import os
from typing import Optional
from urllib.parse import parse_qs

from fastmcp.server.auth import AccessToken, RemoteAuthProvider
from fastmcp.server.auth.providers.introspection import IntrospectionTokenVerifier
from starlette.middleware import Middleware

OAUTH_TOKEN_PREFIX = "dbat_"
MCP_PATH = "/mcp"
SCOPE = "mcp"
INTROSPECTION_CACHE_SECONDS = 60


class DiffbotTokenVerifier(IntrospectionTokenVerifier):
    """Introspects dashboard OAuth tokens and passes static Diffbot API tokens through."""

    def __init__(self, *, resource_url: str, **kwargs):
        super().__init__(**kwargs)
        self.resource_url = resource_url.rstrip("/")

    async def verify_token(self, token: str) -> Optional[AccessToken]:
        if not token.startswith(OAUTH_TOKEN_PREFIX):
            return AccessToken(token=token, client_id="diffbot-api-token", scopes=[SCOPE], claims={"diffbot_token": token})

        access_token = await super().verify_token(token)
        if access_token is None or not access_token.claims.get("diffbot_token"):
            return None
        # Not fastmcp's audience option: the dashboard omits aud when the client sent no
        # RFC 8707 resource, and clients disagree on a trailing slash
        audiences = [aud.rstrip("/") for aud in access_token.claims.get("aud") or []]
        if audiences and self.resource_url not in audiences:
            return None
        return access_token


class QueryTokenMiddleware:
    """Moves ?token= into the Authorization header so URL-configured clients pass the auth check."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and not any(name == b"authorization" for name, _ in scope["headers"]):
            token = parse_qs(scope.get("query_string", b"").decode()).get("token")
            if token:
                scope = {**scope, "headers": [*scope["headers"], (b"authorization", f"Bearer {token[0]}".encode())]}
        await self.app(scope, receive, send)


class DiffbotAuthProvider(RemoteAuthProvider):
    def get_middleware(self):
        return [Middleware(QueryTokenMiddleware), *super().get_middleware()]


def build_auth() -> Optional[DiffbotAuthProvider]:
    issuer = os.getenv("DIFFBOT_OAUTH_ISSUER", "").rstrip("/")
    if not issuer:
        return None
    base_url = os.environ["MCP_BASE_URL"].rstrip("/")
    verifier = DiffbotTokenVerifier(
        introspection_url=f"{issuer}/oauth/introspect/",
        client_id=os.environ["DIFFBOT_OAUTH_CLIENT_ID"],
        client_secret=os.environ["DIFFBOT_OAUTH_CLIENT_SECRET"],
        required_scopes=[SCOPE],
        cache_ttl_seconds=INTROSPECTION_CACHE_SECONDS,
        resource_url=base_url + MCP_PATH,
    )
    return DiffbotAuthProvider(
        token_verifier=verifier,
        authorization_servers=[issuer],
        base_url=base_url,
        resource_name="Diffbot",
    )
