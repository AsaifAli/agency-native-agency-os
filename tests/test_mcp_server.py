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

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


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


def test_streamable_http_mcp_list_and_call_delegate_to_os_tool_gateway(monkeypatch):
    from contextlib import asynccontextmanager

    from fastapi import FastAPI

    identity = SimpleNamespace(
        id="identity-1",
        org_id="org-1",
        workspace_id="workspace-1",
        subject_type="agent",
        scopes=["tools:invoke", "tool:system.health.read"],
        allowed_data_classes=["public"],
    )
    principal = SimpleNamespace(identity=identity)
    session = SimpleNamespace(id=SESSION_ID, data_class="public")
    invoked = {}

    monkeypatch.setattr(
        mcp_server, "authenticate_session_credential",
        lambda _db, _auth, **_kwargs: _context(),
    )
    monkeypatch.setattr(
        mcp_server, "load_active_session_context",
        lambda _db, _context: (principal, session),
    )
    monkeypatch.setattr(
        mcp_server, "_agent_authorized_tool_data_classes",
        lambda _db, _identity: {"system.health.read": {"public"}},
    )

    def invoke(_db, _principal, **kwargs):
        invoked.update(kwargs)
        return {"result": {"status": "ok"}}

    monkeypatch.setattr(mcp_server, "invoke_registered_tool", invoke)

    config = SimpleNamespace(
        claude_managed_mcp_enabled=True,
        claude_managed_mcp_enabled_tool_keys="system.health.read",
        claude_managed_mcp_public_base_url="https://mcp.example.test",
        claude_managed_mcp_max_concurrent_requests=2,
        claude_managed_mcp_max_request_body_bytes=65536,
        claude_managed_mcp_requests_per_minute=30,
    )
    _server, mcp_app, wrapped = mcp_server.create_mcp_gateway(
        config=config, session_factory=FakeDB
    )

    @asynccontextmanager
    async def lifespan(_app):
        async with mcp_app.router.lifespan_context(mcp_app):
            yield

    host_app = FastAPI(lifespan=lifespan)
    host_app.mount("/mcp", wrapped)

    with TestClient(host_app, base_url="https://mcp.example.test") as client:
        auth = {"Authorization": "Bearer aos_ms_test", "Origin": "https://mcp.example.test"}
        initialized = client.post(
            f"/mcp/{SESSION_ID}",
            headers=auth,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "agency-os-test", "version": "1"},
                },
            },
        )
        assert initialized.status_code == 200
        protocol_headers = {**auth, "MCP-Protocol-Version": "2025-11-25"}
        listed = client.post(
            f"/mcp/{SESSION_ID}",
            headers=protocol_headers,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        assert listed.status_code == 200
        listed_tools = listed.json()["result"]["tools"]
        assert [tool["name"] for tool in listed_tools] == ["system.health.read"]

        called = client.post(
            f"/mcp/{SESSION_ID}",
            headers=protocol_headers,
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "system.health.read", "arguments": {}},
            },
        )
        assert called.status_code == 200
        assert called.json()["result"]["content"][0]["text"] == '{"status":"ok"}'

    assert invoked["tool_key"] == "system.health.read"
    assert invoked["session_id"] == SESSION_ID
    assert invoked["allowed_tool_keys"] == {"system.health.read"}
    assert invoked["max_calls_per_session"] == 20
    assert invoked["idempotency_key"].startswith("mcp_")
