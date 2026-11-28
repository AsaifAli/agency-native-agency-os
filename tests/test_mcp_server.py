from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from app import mcp_server
from app.session_credentials import SessionCredentialContext


SESSION_ID = "a1b2c3d4-e5f6-4789-9012-1234567890ab"


class FakeDB:
    def __init__(self):
        self.closed = False
        self.rolled_back = False

    def close(self):
        self.closed = True

    def rollback(self):
        self.rolled_back = True


def _context(session_id=SESSION_ID):
    return SessionCredentialContext(
        org_id="org-1",
        workspace_id="workspace-1",
        machine_identity_id="identity-1",
        session_id=session_id,
        credential_id="credential-1",
        token_hash="0" * 64,
    )


def _middleware_app(monkeypatch, context=None):
    db = FakeDB()
    seen = {}

    async def echo(scope, receive, send):
        seen["path"] = scope["path"]
        await JSONResponse({"path": scope["path"]})(scope, receive, send)

    def authenticate(db_session, authorization, *, requests_per_minute):
        seen["authorization"] = authorization
        seen["requests_per_minute"] = requests_per_minute
        if isinstance(context, Exception):
            raise context
        return context or _context()

    monkeypatch.setattr(mcp_server, "authenticate_session_credential", authenticate)
    app = mcp_server.SessionPathAuthMiddleware(
        echo,
        public_base_url="https://mcp.example.test",
        session_factory=lambda: db,
        requests_per_minute=33,
    )
    return TestClient(app, base_url="https://mcp.example.test"), seen, db


def test_mcp_session_path_is_authenticated_and_rewritten_to_transport_root(monkeypatch):
    client, seen, db = _middleware_app(monkeypatch)
    response = client.post(
        f"/{SESSION_ID}",
        headers={"Authorization": "Bearer aos_ms_test", "Origin": "https://mcp.example.test"},
    )
    assert response.status_code == 200
    assert response.json() == {"path": "/"}
    assert seen["authorization"] == "Bearer aos_ms_test"
    assert seen["requests_per_minute"] == 33
    assert db.closed is True


def test_mcp_session_path_must_match_authenticated_agent_session(monkeypatch):
    client, seen, db = _middleware_app(monkeypatch, _context("b1b2c3d4-e5f6-4789-9012-1234567890ab"))
    response = client.post(
        f"/{SESSION_ID}",
        headers={"Authorization": "Bearer aos_ms_test"},
    )
    assert response.status_code == 401
    assert db.closed is True


@pytest.mark.parametrize(
    "path,headers,expected",
    [
        ("/not-a-session", {"Authorization": "Bearer test"}, 404),
        (f"/{SESSION_ID}", {"Authorization": "Bearer test", "Host": "evil.example.test"}, 421),
        (f"/{SESSION_ID}", {"Authorization": "Bearer test", "Origin": "https://evil.example.test"}, 403),
    ],
)
def test_mcp_transport_rejects_invalid_path_host_and_origin(monkeypatch, path, headers, expected):
    client, _seen, _db = _middleware_app(monkeypatch)
    response = client.post(path, headers=headers)
    assert response.status_code == expected


def test_mcp_transport_returns_429_for_database_session_rate_limit(monkeypatch):
    from fastapi import HTTPException

    client, _seen, db = _middleware_app(monkeypatch, HTTPException(429, "limited"))
    response = client.post(
        f"/{SESSION_ID}",
        headers={"Authorization": "Bearer aos_ms_test"},
    )
    assert response.status_code == 429
    assert db.closed is True


def test_mcp_read_only_discovery_excludes_write_draft_tools(monkeypatch):
    identity = SimpleNamespace(
        id="identity-1",
        org_id="org-1",
        workspace_id="workspace-1",
        subject_type="agent",
        scopes=["tools:invoke", "tool:system.health.read", "tool:revenue.lead.research.capture"],
        allowed_data_classes=["public"],
    )
    principal = SimpleNamespace(identity=identity)
    session = SimpleNamespace(data_class="public")
    monkeypatch.setattr(
        mcp_server,
        "_agent_authorized_tool_data_classes",
        lambda _db, _identity: {"system.health.read": {"public"}, "revenue.lead.research.capture": {"public"}},
    )
    visible = mcp_server._visible_read_only_specs(
        object(),
        principal,
        session,
        enabled_tool_keys=frozenset({"system.health.read", "revenue.lead.research.capture"}),
    )
    assert [spec.key for spec in visible] == ["system.health.read"]


def test_mcp_gateway_rejects_non_read_only_configured_tools():
    config = SimpleNamespace(
        claude_managed_mcp_enabled=True,
        claude_managed_mcp_enabled_tool_keys="revenue.lead.research.capture",
        claude_managed_mcp_public_base_url="https://mcp.example.test",
        claude_managed_mcp_max_concurrent_requests=2,
        claude_managed_mcp_max_request_body_bytes=65536,
        claude_managed_mcp_requests_per_minute=30,
    )
    with pytest.raises(ValueError, match="read-only"):
        mcp_server.create_mcp_gateway(config=config)
