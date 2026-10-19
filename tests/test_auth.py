"""OAuth via the Diffbot dashboard, with static Diffbot API tokens still accepted. No network."""

import time

import httpx2
import pytest
from starlette.testclient import TestClient

from diffbot_mcp import auth
from diffbot_mcp.server import mcp
from diffbot_mcp.tools import extract

OAUTH_ENV = {
    "DIFFBOT_OAUTH_ISSUER": "https://app.diffbot.com",
    "MCP_BASE_URL": "https://mcp.diffbot.com",
    "DIFFBOT_OAUTH_CLIENT_ID": "mcp-server",
    "DIFFBOT_OAUTH_CLIENT_SECRET": "secret",
}
GOOD_TOKEN = "dbat_good"
INITIALIZE = {
    "jsonrpc": "2.0", "id": 0, "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}},
}
CALL_EXTRACT = {
    "jsonrpc": "2.0", "id": 1, "method": "tools/call",
    "params": {"name": "extract", "arguments": {"url": "https://example.com"}},
}
HEADERS = {"Accept": "application/json, text/event-stream"}


class FakeDashboard:
    """Stands in for the dashboard's introspection endpoint."""

    def __init__(self):
        self.calls = 0
        self.aud = ["https://mcp.diffbot.com/mcp"]

    def __call__(self, request):
        self.calls += 1
        assert request.url == "https://app.diffbot.com/oauth/introspect/"
        if b"token=" + GOOD_TOKEN.encode() not in request.content:
            return httpx2.Response(200, json={"active": False})
        data = {"active": True, "client_id": "claude", "scope": "mcp", "exp": int(time.time()) + 3600, "diffbot_token": "user-diffbot-token"}
        if self.aud is not None:
            data["aud"] = self.aud
        return httpx2.Response(200, json=data)


@pytest.fixture
def dashboard(monkeypatch):
    for key, value in OAUTH_ENV.items():
        monkeypatch.setenv(key, value)
    fake = FakeDashboard()
    provider = auth.build_auth()
    provider.token_verifier._http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(fake))
    monkeypatch.setattr(mcp, "auth", provider)
    return fake


@pytest.fixture
def sent_tokens(monkeypatch):
    """Records the Diffbot API token each extract call sends upstream."""
    tokens = []

    async def fake_request(url, *, params=None, **kwargs):
        tokens.append(params["token"])
        return {"objects": []}

    monkeypatch.delenv("DIFFBOT_TOKEN", raising=False)
    monkeypatch.delenv("DIFFBOT_API_TOKEN", raising=False)
    monkeypatch.setattr(extract, "request", fake_request)
    return tokens


@pytest.fixture
def client(dashboard, sent_tokens):
    app = mcp.http_app(stateless_http=True, json_response=True)
    with TestClient(app) as test_client:
        yield test_client


def bearer(token):
    return {**HEADERS, "Authorization": f"Bearer {token}"}


def test_protected_resource_metadata(client):
    response = client.get("/.well-known/oauth-protected-resource/mcp")
    assert response.status_code == 200
    data = response.json()
    assert data["resource"] == "https://mcp.diffbot.com/mcp"
    assert [server.rstrip("/") for server in data["authorization_servers"]] == ["https://app.diffbot.com"]


def test_no_token_challenges_client(client):
    response = client.post("/mcp", json=INITIALIZE, headers=HEADERS)
    assert response.status_code == 401
    assert "resource_metadata=" in response.headers["www-authenticate"]


def test_invalid_oauth_token_rejected(client):
    response = client.post("/mcp", json=INITIALIZE, headers=bearer("dbat_expired"))
    assert response.status_code == 401


def test_oauth_token_uses_users_diffbot_token(client, sent_tokens):
    response = client.post("/mcp", json=CALL_EXTRACT, headers=bearer(GOOD_TOKEN))
    assert response.status_code == 200, response.text
    assert sent_tokens == ["user-diffbot-token"]


@pytest.mark.parametrize("aud", [["https://other.example.com/mcp"], "https://other.example.com/mcp"], ids=["list", "string"])
def test_wrong_audience_rejected(client, dashboard, aud):
    dashboard.aud = aud
    response = client.post("/mcp", json=INITIALIZE, headers=bearer(GOOD_TOKEN))
    assert response.status_code == 401


@pytest.mark.parametrize(
    "aud",
    [["https://mcp.diffbot.com/mcp/"], None, "https://mcp.diffbot.com/mcp"],
    ids=["trailing-slash", "no-resource-sent", "string"],  # RFC 7662 allows aud as a single string
)
def test_lenient_audience_accepted(client, dashboard, aud):
    dashboard.aud = aud
    assert client.post("/mcp", json=INITIALIZE, headers=bearer(GOOD_TOKEN)).status_code == 200


def test_static_bearer_token_still_works(client, sent_tokens):
    response = client.post("/mcp", json=CALL_EXTRACT, headers=bearer("legacy-token"))
    assert response.status_code == 200, response.text
    assert sent_tokens == ["legacy-token"]


def test_query_token_still_works(client, sent_tokens):
    response = client.post("/mcp?token=legacy-token", json=CALL_EXTRACT, headers=HEADERS)
    assert response.status_code == 200, response.text
    assert sent_tokens == ["legacy-token"]


def test_introspection_is_cached(client, dashboard):
    for _ in range(3):
        assert client.post("/mcp", json=INITIALIZE, headers=bearer(GOOD_TOKEN)).status_code == 200
    assert dashboard.calls == 1


def test_auth_disabled_without_issuer(monkeypatch):
    monkeypatch.delenv("DIFFBOT_OAUTH_ISSUER", raising=False)
    assert auth.build_auth() is None
