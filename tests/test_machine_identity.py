import pytest
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import Principal, get_principal
from app.db import Base, get_db
from app.machine_identity import authenticate_machine_token, authorize_tool_session, create_agent_session, expire_due_agent_sessions
from app.models import FounderAuthority, Membership, Organization, Role, User, Workspace
from app.security_models import AgentSession, MachineIdentity, ToolInvocation
from app.security_routes import router
from app.tool_gateway_routes import router as tool_gateway_router


@pytest.fixture()
def security_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    import app.security_models  # noqa: F401
    Base.metadata.create_all(engine)
    db = factory()
    founder = User(email="security-founder@example.test")
    org = Organization(name="Security Test Org")
    db.add_all([founder, org]); db.flush()
    workspace = Workspace(id="security-ws", org_id=org.id, name="Security Workspace")
    db.add_all([workspace, Membership(org_id=org.id, user_id=founder.id, role=Role.owner),
                FounderAuthority(org_id=org.id, user_id=founder.id, active=True)])
    db.commit()
    app = FastAPI()
    app.include_router(router)
    app.include_router(tool_gateway_router)
    def override_db():
        session = factory()
        try: yield session
        finally: session.close()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_principal] = lambda: Principal(user=founder)
    client = TestClient(app)
    client.org_id, client.workspace_id, client.founder = org.id, workspace.id, founder
    client.factory = factory
    yield client
    db.close(); Base.metadata.drop_all(engine); engine.dispose()


def _create_identity(client, scopes=None, classes=None):
    response = client.post(f"/v1/orgs/{client.org_id}/machine-identities", json={
        "workspace_id": client.workspace_id, "name": "Research Worker",
        "subject_type": "worker", "subject_id": "research-worker",
        "scopes": scopes or ["sessions:create", "tools:invoke", "tool:research.read"],
        "allowed_data_classes": classes or ["synthetic", "public"], "ttl_days": 14,
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_machine_secret_is_returned_once_and_only_hash_is_persisted(security_client):
    issued = _create_identity(security_client)
    assert issued["token"].startswith("aos_mi_")
    db = security_client.factory()
    try:
        identity = db.get(MachineIdentity, issued["id"])
        assert issued["token"].split(".", 1)[1] not in identity.token_hash
        assert len(identity.token_hash) == 64
        assert "token_hash" not in issued
    finally:
        db.close()


def test_machine_token_authentication_and_expiry(security_client):
    issued = _create_identity(security_client)
    db = security_client.factory()
    try:
        principal = authenticate_machine_token("Bearer " + issued["token"], db)
        assert principal.identity.id == issued["id"]
        with pytest.raises(Exception):
            authenticate_machine_token("Bearer " + issued["token"] + "wrong", db)
        identity = db.get(MachineIdentity, issued["id"])
        identity.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
        with pytest.raises(Exception):
            authenticate_machine_token("Bearer " + issued["token"], db)
    finally:
        db.close()


def test_machine_session_is_workspace_scoped_and_data_class_bounded(security_client):
    issued = _create_identity(security_client)
    db = security_client.factory()
    try:
        principal = authenticate_machine_token("Bearer " + issued["token"], db)
        session = create_agent_session(db, principal, purpose="Public web research", data_class="public", ttl_seconds=600)
        db.commit()
        assert session.workspace_id == security_client.workspace_id
        assert session.data_class == "public"
        with pytest.raises(Exception):
            create_agent_session(db, principal, purpose="Confidential task", data_class="confidential", ttl_seconds=600)
    finally:
        db.close()


def test_tool_authorization_requires_identity_scope_and_active_session(security_client):
    issued = _create_identity(security_client)
    db = security_client.factory()
    try:
        principal = authenticate_machine_token("Bearer " + issued["token"], db)
        session = create_agent_session(db, principal, purpose="Research", data_class="public", ttl_seconds=600)
        db.commit()
        authorized = authorize_tool_session(db, principal, session_id=session.id, tool_key="research.read", data_class="public")
        assert authorized.id == session.id
        with pytest.raises(Exception):
            authorize_tool_session(db, principal, session_id=session.id, tool_key="crm.write", data_class="public")
        session.status = "cancelled"
        db.commit()
        with pytest.raises(Exception):
            authorize_tool_session(db, principal, session_id=session.id, tool_key="research.read", data_class="public")
    finally:
        db.close()


def test_founder_revocation_cancels_active_sessions(security_client):
    issued = _create_identity(security_client)
    db = security_client.factory()
    principal = authenticate_machine_token("Bearer " + issued["token"], db)
    session = create_agent_session(db, principal, purpose="Research", data_class="public", ttl_seconds=600)
    db.commit(); db.close()
    response = security_client.post(f"/v1/orgs/{security_client.org_id}/machine-identities/{issued['id']}/revoke")
    assert response.status_code == 200, response.text
    db = security_client.factory()
    try:
        assert db.get(MachineIdentity, issued["id"]).revoked_at is not None
        assert db.get(AgentSession, session.id).status == "cancelled"
    finally:
        db.close()


def test_machine_session_route_requires_machine_credential(security_client):
    issued = _create_identity(security_client)
    response = security_client.post("/v1/machine/sessions", json={
        "purpose": "Synthetic test", "data_class": "synthetic", "ttl_seconds": 300,
    })
    assert response.status_code == 401
    response = security_client.post("/v1/machine/sessions",
        headers={"Authorization": "Bearer " + issued["token"]},
        json={"purpose": "Synthetic test", "data_class": "synthetic", "ttl_seconds": 300},
    )
    assert response.status_code == 201, response.text


def test_nonfounder_cannot_issue_machine_identity(security_client):
    from app.models import Membership, Role, User
    from app.auth import get_principal, Principal
    operator = User(email="security-operator@example.test")
    db = security_client.factory()
    try:
        db.add(operator)
        db.flush()
        db.add(Membership(org_id=security_client.org_id, user_id=operator.id, role=Role.operator))
        db.commit()
    finally:
        db.close()
    security_client.app.dependency_overrides[get_principal] = lambda: Principal(user=operator)
    response = security_client.post(
        f"/v1/orgs/{security_client.org_id}/machine-identities",
        json={
            "workspace_id": security_client.workspace_id,
            "name": "Unauthorized Worker",
            "subject_type": "worker",
            "subject_id": "worker-unauthorized",
            "scopes": ["sessions:create"],
            "allowed_data_classes": ["synthetic"],
        },
    )
    assert response.status_code == 403


def test_machine_identity_rejects_commercial_data_until_client_policy_exists(security_client):
    response = security_client.post(
        f"/v1/orgs/{security_client.org_id}/machine-identities",
        json={
            "workspace_id": security_client.workspace_id,
            "name": "Commercial Worker",
            "subject_type": "worker",
            "subject_id": "commercial-worker",
            "scopes": ["sessions:create"],
            "allowed_data_classes": ["commercial"],
        },
    )
    assert response.status_code == 422


def test_machine_session_cannot_outlive_its_identity(security_client):
    issued = _create_identity(security_client)
    db = security_client.factory()
    try:
        principal = authenticate_machine_token("Bearer " + issued["token"], db)
        principal.identity.expires_at = datetime.now(timezone.utc) + timedelta(seconds=180)
        db.flush()
        session = create_agent_session(
            db, principal, purpose="Bounded session", data_class="public", ttl_seconds=3600
        )
        assert session.expires_at <= principal.identity.expires_at
    finally:
        db.close()


def test_revoked_machine_credential_cannot_authenticate(security_client):
    issued = _create_identity(security_client)
    revoked = security_client.post(
        f"/v1/orgs/{security_client.org_id}/machine-identities/{issued['id']}/revoke"
    )
    assert revoked.status_code == 200
    db = security_client.factory()
    try:
        with pytest.raises(Exception):
            authenticate_machine_token("Bearer " + issued["token"], db)
    finally:
        db.close()


def test_session_purpose_is_redacted_and_audited_without_raw_pii(security_client):
    from app.models import AuditEvent
    issued = _create_identity(security_client)
    response = security_client.post(
        "/v1/machine/sessions",
        headers={"Authorization": "Bearer " + issued["token"]},
        json={
            "purpose": "Research for owner@example.test",
            "data_class": "public",
            "ttl_seconds": 300,
        },
    )
    assert response.status_code == 201, response.text
    assert "owner@example.test" not in response.json()["purpose"]
    assert "[REDACTED_EMAIL]" in response.json()["purpose"]
    db = security_client.factory()
    try:
        event = db.query(AuditEvent).filter_by(
            event_type="agent_session.created",
            resource_id=response.json()["id"],
        ).one()
        assert event.payload["purpose_redaction_counts"] == {"EMAIL": 1}
        assert "owner@example.test" not in str(event.payload)
    finally:
        db.close()


def test_session_purpose_with_secret_is_blocked(security_client):
    issued = _create_identity(security_client)
    response = security_client.post(
        "/v1/machine/sessions",
        headers={"Authorization": "Bearer " + issued["token"]},
        json={
            "purpose": "Use token sk-ant-api-1234567890abcdefghijkl",
            "data_class": "public",
            "ttl_seconds": 300,
        },
    )
    assert response.status_code == 422
    assert "blocked by data-protection" in response.json()["detail"]


def _issue_tool_session(client):
    issued = _create_identity(
        client,
        scopes=["sessions:create", "tools:invoke", "tool:system.health.read"],
    )
    headers = {"Authorization": "Bearer " + issued["token"]}
    created = client.post(
        "/v1/machine/sessions",
        headers=headers,
        json={"purpose": "Read system health", "data_class": "public", "ttl_seconds": 600},
    )
    assert created.status_code == 201, created.text
    return issued, created.json()["id"], headers


def test_tool_gateway_executes_registered_read_only_tool_and_persists_audit(security_client):
    from app.models import AuditEvent
    issued, session_id, headers = _issue_tool_session(security_client)
    registry = security_client.get("/v1/machine/tools", headers=headers)
    assert registry.status_code == 200
    assert [tool["key"] for tool in registry.json()["tools"]] == ["system.health.read"]

    response = security_client.post(
        "/v1/machine/tools/system.health.read/invoke",
        headers={**headers, "Idempotency-Key": "health-read-0001"},
        json={"session_id": session_id, "input": {}},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "succeeded"
    assert response.json()["result"] == {"service": "agency-os-api", "database": "ok"}
    assert response.json()["replayed"] is False

    db = security_client.factory()
    try:
        invocation = db.get(ToolInvocation, response.json()["id"])
        assert invocation.machine_identity_id == issued["id"]
        assert invocation.session_id == session_id
        assert invocation.request_payload == {}
        event = db.query(AuditEvent).filter_by(
            event_type="tool.invocation.succeeded",
            resource_id=invocation.id,
        ).one()
        assert event.payload["tool_key"] == "system.health.read"
    finally:
        db.close()


def test_tool_gateway_idempotent_replay_and_session_binding(security_client):
    issued, first_session, headers = _issue_tool_session(security_client)
    first = security_client.post(
        "/v1/machine/tools/system.health.read/invoke",
        headers={**headers, "Idempotency-Key": "health-read-replay-01"},
        json={"session_id": first_session, "input": {}},
    )
    assert first.status_code == 200
    replay = security_client.post(
        "/v1/machine/tools/system.health.read/invoke",
        headers={**headers, "Idempotency-Key": "health-read-replay-01"},
        json={"session_id": first_session, "input": {}},
    )
    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]
    assert replay.json()["replayed"] is True

    second_session_response = security_client.post(
        "/v1/machine/sessions",
        headers=headers,
        json={"purpose": "Another health check", "data_class": "public", "ttl_seconds": 600},
    )
    assert second_session_response.status_code == 201
    conflict = security_client.post(
        "/v1/machine/tools/system.health.read/invoke",
        headers={**headers, "Idempotency-Key": "health-read-replay-01"},
        json={"session_id": second_session_response.json()["id"], "input": {}},
    )
    assert conflict.status_code == 409


def test_tool_gateway_rejects_missing_grants_unregistered_tools_and_bad_payloads(security_client):
    issued = _create_identity(security_client, scopes=["sessions:create"])
    headers = {"Authorization": "Bearer " + issued["token"]}
    created = security_client.post(
        "/v1/machine/sessions",
        headers=headers,
        json={"purpose": "Read health", "data_class": "public", "ttl_seconds": 600},
    )
    assert created.status_code == 201
    session_id = created.json()["id"]

    denied = security_client.post(
        "/v1/machine/tools/system.health.read/invoke",
        headers={**headers, "Idempotency-Key": "health-read-deny-01"},
        json={"session_id": session_id, "input": {}},
    )
    assert denied.status_code == 403

    missing = security_client.post(
        "/v1/machine/tools/system.shell.exec/invoke",
        headers={**headers, "Idempotency-Key": "health-read-missing"},
        json={"session_id": session_id, "input": {}},
    )
    assert missing.status_code == 404


def test_tool_gateway_data_protection_blocks_secret_payload(security_client):
    issued, session_id, headers = _issue_tool_session(security_client)
    blocked = security_client.post(
        "/v1/machine/tools/system.health.read/invoke",
        headers={**headers, "Idempotency-Key": "health-read-secret"},
        json={
            "session_id": session_id,
            "input": {"credential": "sk-ant-api-1234567890abcdefghijkl"},
        },
    )
    assert blocked.status_code == 422
    assert "data-protection" in blocked.json()["detail"]


def test_tool_gateway_rejects_schema_extra_fields(security_client):
    issued, session_id, headers = _issue_tool_session(security_client)
    invalid = security_client.post(
        "/v1/machine/tools/system.health.read/invoke",
        headers={**headers, "Idempotency-Key": "health-read-schema"},
        json={"session_id": session_id, "input": {"arbitrary": "not allowed"}},
    )
    assert invalid.status_code == 422


def test_worker_session_expiry_sweep_marks_and_audits_due_sessions(security_client):
    from app.models import AuditEvent
    issued = _create_identity(security_client)
    db = security_client.factory()
    try:
        principal = authenticate_machine_token("Bearer " + issued["token"], db)
        session = create_agent_session(
            db, principal, purpose="Expire this session", data_class="public", ttl_seconds=600
        )
        db.commit()
        session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
        assert expire_due_agent_sessions(db, limit=10) == 1
        db.commit()
        db.refresh(session)
        assert session.status == "expired"
        event = db.query(AuditEvent).filter_by(
            event_type="agent_session.expired", resource_id=session.id
        ).one()
        assert event.payload["reason_code"] == "SESSION_TTL_EXPIRED"
    finally:
        db.close()
