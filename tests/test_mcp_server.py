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


def test_mcp_discovery_exposes_only_explicitly_granted_draft_tools(monkeypatch):
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
    visible = mcp_server._visible_mcp_specs(
        object(),
        principal,
        session,
        enabled_tool_keys=frozenset({"system.health.read", "revenue.lead.research.capture"}),
    )
    assert [spec.key for spec in visible] == [
        "system.health.read", "revenue.lead.research.capture"
    ]


def test_mcp_gateway_rejects_unknown_configured_tools():
    config = SimpleNamespace(
        claude_managed_mcp_enabled=True,
        claude_managed_mcp_enabled_tool_keys="system.shell.exec",
        claude_managed_mcp_public_base_url="https://mcp.example.test",
        claude_managed_mcp_max_concurrent_requests=2,
        claude_managed_mcp_max_request_body_bytes=65536,
        claude_managed_mcp_requests_per_minute=30,
    )
    with pytest.raises(ValueError, match="registered read-only or pending-draft"):
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
    server, _mcp_app, wrapped = mcp_server.create_mcp_gateway(
        config=config, session_factory=FakeDB
    )

    @asynccontextmanager
    async def lifespan(_app):
        async with server.session_manager.run():
            yield

    host_app = FastAPI(lifespan=lifespan)
    host_app.mount("/mcp", wrapped)

    with TestClient(host_app, base_url="https://mcp.example.test") as client:
        auth = {
            "Authorization": "Bearer aos_ms_test",
            "Origin": "https://mcp.example.test",
            "Accept": "application/json, text/event-stream",
        }
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


def test_mcp_discovery_supports_founder_provisioned_service_identity_without_agent_grants(monkeypatch):
    identity = SimpleNamespace(
        id="identity-2",
        org_id="org-1",
        workspace_id="workspace-1",
        subject_type="service",
        scopes=[
            "tools:invoke", "tool:system.health.read", "tool:workspace.knowledge.search"
        ],
        allowed_data_classes=["public"],
    )
    principal = SimpleNamespace(identity=identity)
    session = SimpleNamespace(data_class="public")

    visible = mcp_server._visible_mcp_specs(
        object(),
        principal,
        session,
        enabled_tool_keys=frozenset({"system.health.read", "workspace.knowledge.search"}),
    )

    assert [spec.key for spec in visible] == [
        "workspace.knowledge.search", "system.health.read"
    ]


def test_mcp_discovery_keeps_service_identity_limited_to_its_machine_scopes():
    identity = SimpleNamespace(
        id="identity-3",
        org_id="org-1",
        workspace_id="workspace-1",
        subject_type="service",
        scopes=["tools:invoke"],
        allowed_data_classes=["public"],
    )
    principal = SimpleNamespace(identity=identity)
    session = SimpleNamespace(data_class="public")

    visible = mcp_server._visible_mcp_specs(
        object(),
        principal,
        session,
        enabled_tool_keys=frozenset({"system.health.read"}),
    )

    assert visible == []


def test_streamable_http_mcp_supports_founder_scoped_service_identity_draft_handoff(monkeypatch):
    from contextlib import asynccontextmanager

    from fastapi import FastAPI

    identity = SimpleNamespace(
        id="service-identity-1",
        org_id="org-1",
        workspace_id="workspace-1",
        subject_type="service",
        scopes=[
            "sessions:create", "tools:invoke",
            "tool:revenue.lead.research.capture",
        ],
        allowed_data_classes=["public"],
    )
    principal = SimpleNamespace(identity=identity)
    session = SimpleNamespace(id=SESSION_ID, data_class="public")
    invoked = {}

    machine_context = mcp_server.MachineIdentitySessionContext(
        org_id="org-1", workspace_id="workspace-1",
        machine_identity_id="service-identity-1", session_id=SESSION_ID,
        token_hash="a" * 64,
    )
    monkeypatch.setattr(
        mcp_server, "authenticate_machine_session",
        lambda _db, _auth, _session_id: machine_context,
    )
    monkeypatch.setattr(
        mcp_server, "load_mcp_session_context",
        lambda _db, _context: (principal, session),
    )

    def invoke(_db, _principal, **kwargs):
        invoked.update(kwargs)
        return {"result": {"draft_id": "draft-123", "status": "pending_review"}}

    monkeypatch.setattr(mcp_server, "invoke_registered_tool", invoke)
    config = SimpleNamespace(
        agency_mcp_enabled=True,
        agency_mcp_enabled_tool_keys="revenue.lead.research.capture",
        agency_mcp_public_base_url="https://mcp.example.test",
        agency_mcp_max_concurrent_requests=2,
        agency_mcp_max_request_body_bytes=65536,
        agency_mcp_requests_per_minute=30,
    )
    server, _mcp_app, wrapped = mcp_server.create_mcp_gateway(
        config=config, session_factory=FakeDB
    )

    @asynccontextmanager
    async def lifespan(_app):
        async with server.session_manager.run():
            yield

    host_app = FastAPI(lifespan=lifespan)
    host_app.mount("/mcp", wrapped)
    with TestClient(host_app, base_url="https://mcp.example.test") as client:
        auth = {
            "Authorization": "Bearer aos_mi_service-test",
            "Origin": "https://mcp.example.test",
            "Accept": "application/json, text/event-stream",
        }
        client.post(
            f"/mcp/{SESSION_ID}", headers=auth,
            json={
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25", "capabilities": {},
                    "clientInfo": {"name": "cowork-service-test", "version": "1"},
                },
            },
        )
        protocol_headers = {**auth, "MCP-Protocol-Version": "2025-11-25"}
        listed = client.post(
            f"/mcp/{SESSION_ID}", headers=protocol_headers,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        assert listed.status_code == 200
        assert [item["name"] for item in listed.json()["result"]["tools"]] == [
            "revenue.lead.research.capture"
        ]
        called = client.post(
            f"/mcp/{SESSION_ID}", headers=protocol_headers,
            json={
                "jsonrpc": "2.0", "id": 3, "method": "tools/call",
                "params": {
                    "name": "revenue.lead.research.capture",
                    "arguments": {
                        "company_name": "Example Company",
                        "summary": "Publicly sourced company research for founder review.",
                        "source_references": ["https://example.com/company"],
                        "fit_score": 80,
                        "confidence_score": 75,
                        "buying_signals": [],
                        "risks": [],
                    },
                },
            },
        )
        assert called.status_code == 200
        assert "pending_review" in called.json()["result"]["content"][0]["text"]

    assert invoked["tool_key"] == "revenue.lead.research.capture"
    assert invoked["max_calls_per_session"] == 20
    assert invoked["allowed_tool_keys"] == {"revenue.lead.research.capture"}


def test_modern_stateless_mcp_protocol_discovery_list_and_call(monkeypatch):
    """2026-07-28 clients must work without initialize or protocol session IDs."""
    from contextlib import asynccontextmanager
    from fastapi import FastAPI
    from mcp.shared.inbound import (
        MCP_METHOD_HEADER,
        MCP_NAME_HEADER,
        MCP_PROTOCOL_VERSION_HEADER,
    )
    from mcp_types import (
        CLIENT_CAPABILITIES_META_KEY,
        CLIENT_INFO_META_KEY,
        PROTOCOL_VERSION_META_KEY,
    )

    identity = SimpleNamespace(
        id="identity-modern", org_id="org-1", workspace_id="workspace-1",
        subject_type="service",
        scopes=["tools:invoke", "sessions:create", "tool:system.health.read"],
        allowed_data_classes=["public"],
    )
    principal = SimpleNamespace(identity=identity)
    session = SimpleNamespace(id=SESSION_ID, data_class="public")
    context = mcp_server.MachineIdentitySessionContext(
        org_id="org-1", workspace_id="workspace-1",
        machine_identity_id="identity-modern", session_id=SESSION_ID,
        token_hash="b" * 64,
    )
    monkeypatch.setattr(
        mcp_server, "authenticate_machine_session",
        lambda _db, _auth, _session_id: context,
    )
    monkeypatch.setattr(
        mcp_server, "load_mcp_session_context",
        lambda _db, _context: (principal, session),
    )
    invocations = []
    def invoke_registered_tool(*_args, **_kwargs):
        invocations.append(True)
        return {"result": {"status": "ok"}}
    monkeypatch.setattr(mcp_server, "invoke_registered_tool", invoke_registered_tool)
    monkeypatch.setattr(
        mcp_server, "_visible_mcp_specs",
        lambda *_a, **_kw: [mcp_server.get_tool("system.health.read")],
    )
    config = SimpleNamespace(
        agency_mcp_enabled=True,
        agency_mcp_enabled_tool_keys="system.health.read",
        agency_mcp_public_base_url="https://mcp.example.test",
        agency_mcp_max_concurrent_requests=2,
        agency_mcp_max_request_body_bytes=65536,
        agency_mcp_requests_per_minute=30,
    )
    server, _mcp_app, wrapped = mcp_server.create_mcp_gateway(
        config=config, session_factory=FakeDB
    )

    @asynccontextmanager
    async def lifespan(_app):
        async with server.session_manager.run():
            yield

    host_app = FastAPI(lifespan=lifespan)
    host_app.mount("/mcp", wrapped)
    base_headers = {
        "Authorization": "Bearer aos_mi_service-test",
        "Origin": "https://mcp.example.test",
        "Accept": "application/json",
        MCP_PROTOCOL_VERSION_HEADER: "2026-07-28",
    }
    meta = {
        PROTOCOL_VERSION_META_KEY: "2026-07-28",
        CLIENT_CAPABILITIES_META_KEY: {"extensions": {}},
        CLIENT_INFO_META_KEY: {"name": "agency-os-modern-test", "version": "1"},
    }

    with TestClient(host_app, base_url="https://mcp.example.test") as client:
        discovered = client.post(
            f"/mcp/{SESSION_ID}",
            headers={**base_headers, MCP_METHOD_HEADER: "server/discover"},
            json={"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {"_meta": meta}},
        )
        assert discovered.status_code == 200
        assert discovered.json()["result"]
        assert "Mcp-Session-Id" not in discovered.headers

        listed = client.post(
            f"/mcp/{SESSION_ID}",
            headers={**base_headers, MCP_METHOD_HEADER: "tools/list"},
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {"_meta": meta}},
        )
        assert listed.status_code == 200
        assert [tool["name"] for tool in listed.json()["result"]["tools"]] == ["system.health.read"]
        assert "Mcp-Session-Id" not in listed.headers

        called = client.post(
            f"/mcp/{SESSION_ID}",
            headers={
                **base_headers,
                MCP_METHOD_HEADER: "tools/call",
                MCP_NAME_HEADER: "system.health.read",
            },
            json={
                "jsonrpc": "2.0", "id": 3, "method": "tools/call",
                "params": {"name": "system.health.read", "arguments": {}, "_meta": meta},
            },
        )
        assert called.status_code == 200
        assert called.json()["result"]["content"][0]["text"] == '{"status":"ok"}'
        assert "Mcp-Session-Id" not in called.headers

        mismatched_method = client.post(
            f"/mcp/{SESSION_ID}",
            headers={**base_headers, MCP_METHOD_HEADER: "tools/list"},
            json={
                "jsonrpc": "2.0", "id": 4, "method": "tools/call",
                "params": {"name": "system.health.read", "arguments": {}, "_meta": meta},
            },
        )
        assert mismatched_method.status_code == 400

        mismatched_name = client.post(
            f"/mcp/{SESSION_ID}",
            headers={
                **base_headers,
                MCP_METHOD_HEADER: "tools/call",
                MCP_NAME_HEADER: "workspace.knowledge.search",
            },
            json={
                "jsonrpc": "2.0", "id": 5, "method": "tools/call",
                "params": {"name": "system.health.read", "arguments": {}, "_meta": meta},
            },
        )
        assert mismatched_name.status_code == 400
        assert len(invocations) == 1
