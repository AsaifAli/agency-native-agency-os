import pytest
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import Principal, get_principal
from app.db import Base, get_db, set_rls_context
from app.machine_identity import authenticate_machine_token, authorize_tool_session, create_agent_session, expire_due_agent_sessions
from app.models import FounderAuthority, Membership, Organization, Role, User, Workspace, WorkspaceGrant
from app.security_models import AgentSession, MachineIdentity, ToolInvocation
from app.security_routes import router
from app.tool_gateway_routes import router as tool_gateway_router
from app.revenue_research_routes import router as revenue_research_router


@pytest.fixture()
def security_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    import app.models  # noqa: F401
    import app.domain_models  # noqa: F401
    import app.telephony.models  # noqa: F401
    import app.operations_models  # noqa: F401
    import app.outreach.models  # noqa: F401
    import app.workforce_models  # noqa: F401
    import app.security_models  # noqa: F401
    import app.private_ops_models  # noqa: F401
    Base.metadata.create_all(engine)
    db = factory()
    founder = User(email="security-founder@example.test")
    org = Organization(name="Security Test Org")
    db.add_all([founder, org]); db.flush()
    workspace = Workspace(id="security-ws", org_id=org.id, name="Security Workspace")
    db.add_all([workspace, Membership(org_id=org.id, user_id=founder.id, role=Role.owner),
                FounderAuthority(org_id=org.id, user_id=founder.id, active=True)])
    db.add(WorkspaceGrant(
        org_id=org.id, workspace_id=workspace.id,
        user_id=founder.id, granted_by=founder.id,
    ))
    db.commit()
    app = FastAPI()
    app.include_router(router)
    app.include_router(tool_gateway_router)
    app.include_router(revenue_research_router)
    principal = {"user": founder}
    def override_db():
        session = factory()
        try:
            set_rls_context(session, user_id=principal["user"].id)
            yield session
        finally:
            session.close()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_principal] = lambda: Principal(user=principal["user"])
    client = TestClient(app)
    original_request = client.request

    def workspace_scoped_request(method, url, **kwargs):
        url_text = str(url)
        params = kwargs.get("params")
        if "/v1/orgs/" in url_text and "workspace_id=" not in url_text:
            scoped_params = dict(params or {})
            scoped_params.setdefault("workspace_id", workspace.id)
            kwargs["params"] = scoped_params
        return original_request(method, url, **kwargs)

    client.request = workspace_scoped_request
    client.org_id, client.workspace_id, client.founder = org.id, workspace.id, founder
    client.factory = factory
    client.set_principal = lambda selected_user: principal.update(user=selected_user)
    yield client
    db.close(); Base.metadata.drop_all(engine); engine.dispose()


def _create_identity(client, scopes=None, classes=None, subject_type="worker"):
    response = client.post(f"/v1/orgs/{client.org_id}/machine-identities", json={
        "workspace_id": client.workspace_id, "name": "Research Worker",
        "subject_type": subject_type, "subject_id": "research-worker",
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
        assert db.info["agency_os_rls_context"]["machine_identity_lookup_id"] == issued["id"]
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
        db.add(WorkspaceGrant(
            org_id=security_client.org_id, workspace_id=security_client.workspace_id,
            user_id=operator.id, granted_by=security_client.founder.id,
        ))
        db.commit()
    finally:
        db.close()
    security_client.set_principal(operator)
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


def _issue_tool_session(client, subject_type="worker"):
    issued = _create_identity(
        client,
        scopes=["sessions:create", "tools:invoke", "tool:system.health.read"],
        subject_type=subject_type,
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

    # Once payload retention expires, the tombstone must reject replay rather
    # than re-execute a tool whose original result has been scrubbed.
    db = security_client.factory()
    try:
        invocation = db.query(ToolInvocation).filter_by(id=first.json()["id"]).one()
        invocation.request_payload = {}
        invocation.result = None
        invocation.payload_purged_at = datetime.now(timezone.utc) - timedelta(days=181)
        db.commit()
    finally:
        db.close()
    expired_replay = security_client.post(
        "/v1/machine/tools/system.health.read/invoke",
        headers={**headers, "Idempotency-Key": "health-read-replay-01"},
        json={"session_id": first_session, "input": {}},
    )
    assert expired_replay.status_code == 410
    assert expired_replay.json()["detail"] == "IDEMPOTENCY_RESULT_EXPIRED"

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
    issued = _create_identity(security_client, scopes=["sessions:create", "tools:invoke", "tool:system.shell.exec"])
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


def _issue_research_session(client):
    issued = _create_identity(
        client,
        scopes=[
            "sessions:create",
            "tools:invoke",
            "tool:revenue.lead.research.capture",
        ],
        classes=["public"],
    )
    headers = {"Authorization": "Bearer " + issued["token"]}
    session = client.post(
        "/v1/machine/sessions",
        headers=headers,
        json={"purpose": "Capture public company research", "data_class": "public", "ttl_seconds": 600},
    )
    assert session.status_code == 201, session.text
    return issued, session.json()["id"], headers


def _research_payload():
    return {
        "company_name": "Acme Robotics",
        "summary": "Builds autonomous industrial inspection systems and is expanding its engineering operations.",
        "source_references": ["https://example.com/news/robotics-expansion"],
        "fit_score": 82,
        "confidence_score": 91,
        "buying_signals": ["Hiring machine learning engineers", "Announced a new facility"],
        "risks": ["No public budget evidence"],
    }


def test_revenue_research_tool_creates_public_draft_without_creating_crm_contact(security_client):
    from app.domain_models import Lead, LeadResearchDraft
    issued, session_id, headers = _issue_research_session(security_client)
    response = security_client.post(
        "/v1/machine/tools/revenue.lead.research.capture/invoke",
        headers={**headers, "Idempotency-Key": "revenue-research-0001"},
        json={"session_id": session_id, "input": _research_payload()},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "succeeded"
    draft_id = response.json()["result"]["draft_id"]
    db = security_client.factory()
    try:
        draft = db.get(LeadResearchDraft, draft_id)
        assert draft.machine_identity_id == issued["id"]
        assert draft.status == "pending_review"
        assert draft.source_references == ["https://example.com/news/robotics-expansion"]
        assert db.query(Lead).filter_by(org_id=security_client.org_id, workspace_id=security_client.workspace_id).count() == 0
    finally:
        db.close()


def test_founder_approves_and_promotes_research_draft_to_crm(security_client):
    from app.domain_models import Lead, LeadResearchDraft, LeadResearchRecord
    issued, session_id, headers = _issue_research_session(security_client)
    captured = security_client.post(
        "/v1/machine/tools/revenue.lead.research.capture/invoke",
        headers={**headers, "Idempotency-Key": "revenue-research-0002"},
        json={"session_id": session_id, "input": _research_payload()},
    )
    assert captured.status_code == 200, captured.text
    draft_id = captured.json()["result"]["draft_id"]
    base = f"/v1/orgs/{security_client.org_id}/workspaces/{security_client.workspace_id}/lead-research-drafts"
    listing = security_client.get(base)
    assert listing.status_code == 200 and listing.json()["items"][0]["id"] == draft_id
    reviewed = security_client.post(
        f"{base}/{draft_id}/review",
        json={"decision": "approve", "review_note": "Evidence is sufficient for CRM entry."},
    )
    assert reviewed.status_code == 200 and reviewed.json()["status"] == "approved"
    promoted = security_client.post(f"{base}/{draft_id}/promote")
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["status"] == "promoted"
    replay = security_client.post(f"{base}/{draft_id}/promote")
    assert replay.status_code == 200 and replay.json()["replayed"] is True
    db = security_client.factory()
    try:
        draft = db.get(LeadResearchDraft, draft_id)
        lead = db.get(Lead, promoted.json()["lead_id"])
        research = db.query(LeadResearchRecord).filter_by(lead_id=lead.id).one()
        assert draft.status == "promoted" and draft.promoted_lead_id == lead.id
        assert lead.company_name == "Acme Robotics" and lead.source == "agent_research"
        assert research.fit_score == 82 and research.confidence_score == 91
    finally:
        db.close()


def test_revenue_research_tool_rejects_private_or_non_https_sources(security_client):
    issued, session_id, headers = _issue_research_session(security_client)
    payload = _research_payload()
    payload["source_references"] = ["http://127.0.0.1/private"]
    response = security_client.post(
        "/v1/machine/tools/revenue.lead.research.capture/invoke",
        headers={**headers, "Idempotency-Key": "revenue-research-private"},
        json={"session_id": session_id, "input": payload},
    )
    assert response.status_code == 422


def test_revenue_research_tool_rejects_contact_fields_and_redacts_pii(security_client):
    issued, session_id, headers = _issue_research_session(security_client)
    payload = _research_payload()
    payload["contact_email"] = "owner@example.test"
    invalid = security_client.post(
        "/v1/machine/tools/revenue.lead.research.capture/invoke",
        headers={**headers, "Idempotency-Key": "revenue-research-contact"},
        json={"session_id": session_id, "input": payload},
    )
    assert invalid.status_code == 422

    payload = _research_payload()
    payload["summary"] += " Contact details listed as owner@example.test."
    response = security_client.post(
        "/v1/machine/tools/revenue.lead.research.capture/invoke",
        headers={**headers, "Idempotency-Key": "revenue-research-pii"},
        json={"session_id": session_id, "input": payload},
    )
    assert response.status_code == 200, response.text
    from app.domain_models import LeadResearchDraft
    db = security_client.factory()
    try:
        draft = db.get(LeadResearchDraft, response.json()["result"]["draft_id"])
        assert "owner@example.test" not in draft.summary
        assert "[REDACTED_EMAIL]" in draft.summary
    finally:
        db.close()


def test_nonfounder_cannot_review_agent_research_draft(security_client):
    from app.models import Membership, Role, User
    from app.auth import get_principal, Principal
    issued, session_id, headers = _issue_research_session(security_client)
    captured = security_client.post(
        "/v1/machine/tools/revenue.lead.research.capture/invoke",
        headers={**headers, "Idempotency-Key": "revenue-research-review-auth"},
        json={"session_id": session_id, "input": _research_payload()},
    )
    draft_id = captured.json()["result"]["draft_id"]
    operator = User(email="research-operator@example.test")
    db = security_client.factory()
    try:
        db.add(operator); db.flush()
        db.add(Membership(org_id=security_client.org_id, user_id=operator.id, role=Role.operator))
        db.add(WorkspaceGrant(
            org_id=security_client.org_id, workspace_id=security_client.workspace_id,
            user_id=operator.id, granted_by=security_client.founder.id,
        ))
        db.commit()
    finally:
        db.close()
    security_client.set_principal(operator)
    base = f"/v1/orgs/{security_client.org_id}/workspaces/{security_client.workspace_id}/lead-research-drafts"
    denied = security_client.post(f"{base}/{draft_id}/review", json={"decision": "approve"})
    assert denied.status_code == 403


def test_rejected_research_draft_cannot_be_promoted(security_client):
    issued, session_id, headers = _issue_research_session(security_client)
    captured = security_client.post(
        "/v1/machine/tools/revenue.lead.research.capture/invoke",
        headers={**headers, "Idempotency-Key": "revenue-research-rejected"},
        json={"session_id": session_id, "input": _research_payload()},
    )
    assert captured.status_code == 200
    draft_id = captured.json()["result"]["draft_id"]
    base = f"/v1/orgs/{security_client.org_id}/workspaces/{security_client.workspace_id}/lead-research-drafts"
    rejected = security_client.post(
        f"{base}/{draft_id}/review",
        json={"decision": "reject", "review_note": "Insufficient evidence."},
    )
    assert rejected.status_code == 200 and rejected.json()["status"] == "rejected"
    promoted = security_client.post(f"{base}/{draft_id}/promote")
    assert promoted.status_code == 409


def test_revenue_research_tool_rejects_duplicate_source_references(security_client):
    issued, session_id, headers = _issue_research_session(security_client)
    payload = _research_payload()
    payload["source_references"] = [payload["source_references"][0], payload["source_references"][0]]
    response = security_client.post(
        "/v1/machine/tools/revenue.lead.research.capture/invoke",
        headers={**headers, "Idempotency-Key": "revenue-research-duplicate-source"},
        json={"session_id": session_id, "input": payload},
    )
    assert response.status_code == 422



def _seed_worker_execution_and_identity(security_client):
    from app.machine_identity import issue_machine_credential
    from app.models import Agent, DataClass, Execution, ExecutionAttempt, ExecutionAttemptStatus, ExecutionStatus, Task
    from app.workforce_models import WorkforceMember, WorkforceCapability

    now = datetime.now(timezone.utc)
    _secret, token_hash, token_prefix = issue_machine_credential()
    db = security_client.factory()
    try:
        agent = Agent(
            id="agent-research-worker",
            org_id=security_client.org_id,
            workspace_id=security_client.workspace_id,
            name="Research Worker",
            department="Business Development",
            instructions="Capture evidence-backed public research.",
            runtime="claude_managed_agents",
            data_class=DataClass.public,
            enabled=True,
        )
        task = Task(
            id="task-research-worker",
            org_id=security_client.org_id,
            workspace_id=security_client.workspace_id,
            title="Research target company",
            description="Capture public research for a target company.",
            created_by=security_client.founder.id,
        )
        identity = MachineIdentity(
            org_id=security_client.org_id,
            workspace_id=security_client.workspace_id,
            name="Research Worker Runtime",
            subject_type="agent",
            subject_id=agent.id,
            token_hash=token_hash,
            token_prefix=token_prefix,
            scopes=[
                "sessions:create",
                "tools:invoke",
                "tool:revenue.lead.research.capture",
            ],
            allowed_data_classes=["public"],
            expires_at=now + timedelta(days=30),
            created_by_user_id=security_client.founder.id,
        )
        execution = Execution(
            id="execution-research-worker",
            org_id=security_client.org_id,
            workspace_id=security_client.workspace_id,
            task_id=task.id,
            agent_id=agent.id,
            requested_by=security_client.founder.id,
            idempotency_key="research-worker-execution-001",
            runtime="claude_managed_agents",
            data_class=DataClass.public,
            client_authorized=False,
            status=ExecutionStatus.running,
            request_metadata={},
        )
        attempt = ExecutionAttempt(
            execution_id=execution.id,
            attempt_number=1,
            worker_id="worker-research-worker",
            runtime="claude_managed_agents",
            status=ExecutionAttemptStatus.running,
            lease_expires_at=now + timedelta(minutes=5),
        )
        member = WorkforceMember(
            org_id=security_client.org_id,
            workspace_id=security_client.workspace_id,
            agent_id=agent.id,
            member_type="agent",
            name="Research Worker",
            title="Lead Research Specialist",
            department_key="business_development_sales",
            responsibilities=["Capture public research"],
            autonomy_level=1,
            status="active",
            is_founder_reserved=False,
        )
        db.add(member)
        db.flush()
        capability = WorkforceCapability(
            org_id=security_client.org_id,
            workspace_id=security_client.workspace_id,
            member_id=member.id,
            capability_key="public_lead_research",
            scope="workspace",
            allowed_data_classes=["public"],
            allowed_actions=["research.execute"],
            tool_allowlist=["revenue.lead.research.capture"],
            budget_minor=0,
            currency="INR",
            enabled=True,
        )
        db.add_all([agent, task, identity, execution, attempt, capability])
        db.commit()
        return agent.id, execution.id, identity.id, attempt.id
    finally:
        db.close()


def test_worker_custom_tool_executor_persists_session_and_replays_idempotently(security_client):
    from app.domain_models import LeadResearchDraft
    from app.integrations.runtime import ExecutionRequest
    from app.models import DataClass, Execution
    from app.worker.tool_executor import build_machine_tool_executor

    _agent_id, execution_id, identity_id, attempt_id = _seed_worker_execution_and_identity(security_client)
    request = ExecutionRequest(
        org_id=security_client.org_id,
        workspace_id=security_client.workspace_id,
        task_id="task-research-worker",
        agent_id="agent-research-worker",
        data_class=DataClass.public,
        task_title="Research target company",
    )
    executor = build_machine_tool_executor(
        session_factory=security_client.factory,
        request=request,
        execution_id=execution_id,
        attempt_id=attempt_id,
        worker_id="worker-research-worker",
        session_ttl_seconds=600,
    )
    first = executor("os_revenue_lead_research_capture", _research_payload(), "sevt_worker_tool_1")
    db = security_client.factory()
    try:
        execution = db.get(Execution, execution_id)
        previous_session = db.get(AgentSession, execution.machine_session_id)
        previous_session.status = "expired"
        previous_session.ended_at = datetime.now(timezone.utc)
        db.commit()
        previous_session_id = previous_session.id
    finally:
        db.close()
    # The provider retries the same event after OS session renewal. Authorization
    # must use the new live session, while idempotency remains execution-scoped.
    replay = executor("os_revenue_lead_research_capture", _research_payload(), "sevt_worker_tool_1")
    assert first["status"] == "pending_review"
    assert replay["draft_id"] == first["draft_id"]

    db = security_client.factory()
    try:
        execution = db.get(Execution, execution_id)
        session = db.get(AgentSession, execution.machine_session_id)
        invocation = db.query(ToolInvocation).filter_by(
            machine_identity_id=identity_id,
            tool_key="revenue.lead.research.capture",
        ).one()
        drafts = db.query(LeadResearchDraft).filter_by(
            org_id=security_client.org_id,
            workspace_id=security_client.workspace_id,
        ).all()
        assert session.machine_identity_id == identity_id
        assert session.status == "active"
        assert session.id != previous_session_id
        assert invocation.status == "succeeded"
        assert len(drafts) == 1 and drafts[0].id == first["draft_id"]
    finally:
        db.close()


def test_worker_custom_tool_executor_rejects_revoked_machine_identity(security_client):
    from app.integrations.runtime import ExecutionRequest
    from app.models import DataClass
    from app.worker.tool_executor import build_machine_tool_executor, ToolExecutionRejected

    _agent_id, execution_id, identity_id, attempt_id = _seed_worker_execution_and_identity(security_client)
    db = security_client.factory()
    try:
        identity = db.get(MachineIdentity, identity_id)
        identity.revoked_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()

    request = ExecutionRequest(
        org_id=security_client.org_id,
        workspace_id=security_client.workspace_id,
        task_id="task-research-worker",
        agent_id="agent-research-worker",
        data_class=DataClass.public,
        task_title="Research target company",
    )
    executor = build_machine_tool_executor(
        session_factory=security_client.factory,
        request=request,
        execution_id=execution_id,
        attempt_id=attempt_id,
        worker_id="worker-research-worker",
        session_ttl_seconds=600,
    )
    with pytest.raises(ToolExecutionRejected):
        executor("os_revenue_lead_research_capture", _research_payload(), "sevt_revoked_identity")


def test_worker_custom_tool_executor_rejects_abandoned_execution_attempt(security_client):
    from app.integrations.runtime import ExecutionRequest
    from app.models import DataClass, ExecutionAttempt, ExecutionAttemptStatus
    from app.worker.tool_executor import build_machine_tool_executor, ToolExecutionRejected

    _agent_id, execution_id, _identity_id, attempt_id = _seed_worker_execution_and_identity(security_client)
    db = security_client.factory()
    try:
        db.get(ExecutionAttempt, attempt_id).status = ExecutionAttemptStatus.abandoned
        db.commit()
    finally:
        db.close()

    request = ExecutionRequest(
        org_id=security_client.org_id,
        workspace_id=security_client.workspace_id,
        task_id="task-research-worker",
        agent_id="agent-research-worker",
        data_class=DataClass.public,
        task_title="Research target company",
    )
    executor = build_machine_tool_executor(
        session_factory=security_client.factory,
        request=request,
        execution_id=execution_id,
        attempt_id=attempt_id,
        worker_id="worker-research-worker",
        session_ttl_seconds=600,
    )
    with pytest.raises(ToolExecutionRejected):
        executor("os_revenue_lead_research_capture", _research_payload(), "sevt_abandoned_attempt")


def test_provider_event_idempotency_is_scoped_to_os_execution(security_client):
    from app.domain_models import LeadResearchDraft
    from app.integrations.runtime import ExecutionRequest
    from app.models import DataClass, Execution, ExecutionAttempt, ExecutionAttemptStatus, ExecutionStatus
    from app.worker.tool_executor import build_machine_tool_executor

    _agent_id, first_execution_id, identity_id, first_attempt_id = _seed_worker_execution_and_identity(security_client)
    db = security_client.factory()
    try:
        first_execution = db.get(Execution, first_execution_id)
        second_execution = Execution(
            id="execution-research-worker-second",
            org_id=first_execution.org_id,
            workspace_id=first_execution.workspace_id,
            task_id=first_execution.task_id,
            agent_id=first_execution.agent_id,
            requested_by=first_execution.requested_by,
            idempotency_key="research-worker-execution-002",
            runtime=first_execution.runtime,
            data_class=first_execution.data_class,
            client_authorized=False,
            status=ExecutionStatus.running,
            request_metadata={},
        )
        second_attempt = ExecutionAttempt(
            execution_id=second_execution.id,
            attempt_number=1,
            worker_id="worker-research-worker-2",
            runtime="claude_managed_agents",
            status=ExecutionAttemptStatus.running,
            lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        db.add_all([second_execution, second_attempt])
        db.commit()
        second_attempt_id = second_attempt.id
    finally:
        db.close()

    request = ExecutionRequest(
        org_id=security_client.org_id,
        workspace_id=security_client.workspace_id,
        task_id="task-research-worker",
        agent_id="agent-research-worker",
        data_class=DataClass.public,
        task_title="Research target company",
    )
    first_executor = build_machine_tool_executor(
        session_factory=security_client.factory,
        request=request,
        execution_id=first_execution_id,
        attempt_id=first_attempt_id,
        worker_id="worker-research-worker",
        session_ttl_seconds=600,
    )
    second_executor = build_machine_tool_executor(
        session_factory=security_client.factory,
        request=request,
        execution_id="execution-research-worker-second",
        attempt_id=second_attempt_id,
        worker_id="worker-research-worker-2",
        session_ttl_seconds=600,
    )
    first = first_executor(
        "os_revenue_lead_research_capture", _research_payload(), "sevt_reused_across_executions"
    )
    second = second_executor(
        "os_revenue_lead_research_capture", _research_payload(), "sevt_reused_across_executions"
    )
    assert first["draft_id"] != second["draft_id"]

    db = security_client.factory()
    try:
        assert db.query(ToolInvocation).filter_by(machine_identity_id=identity_id).count() == 2
        assert db.query(LeadResearchDraft).filter_by(
            org_id=security_client.org_id,
            workspace_id=security_client.workspace_id,
        ).count() == 2
    finally:
        db.close()


def test_execution_machine_session_mapping_uses_composite_workspace_scope():
    from app.models import Execution

    foreign_key = next(
        constraint for constraint in Execution.__table__.constraints
        if constraint.name == "fk_execution_machine_session_scope"
    )
    unique_key = next(
        constraint for constraint in Execution.__table__.constraints
        if constraint.name == "uq_execution_machine_session_scope"
    )
    assert [column.name for column in foreign_key.columns] == [
        "org_id", "workspace_id", "machine_session_id",
    ]
    assert [element.column.name for element in foreign_key.elements] == [
        "org_id", "workspace_id", "id",
    ]
    assert [column.name for column in unique_key.columns] == [
        "org_id", "workspace_id", "machine_session_id",
    ]

def test_lead_research_draft_model_matches_promoted_lead_migration():
    from app.domain_models import LeadResearchDraft
    assert "promoted_lead_id" in LeadResearchDraft.__table__.columns


def test_worker_custom_tool_executor_rechecks_paused_workforce_member(security_client):
    from app.integrations.runtime import ExecutionRequest
    from app.models import DataClass
    from app.workforce_models import WorkforceMember
    from app.worker.tool_executor import build_machine_tool_executor, ToolExecutionRejected

    _agent_id, execution_id, _identity_id, attempt_id = _seed_worker_execution_and_identity(security_client)
    db = security_client.factory()
    try:
        member = db.query(WorkforceMember).filter_by(agent_id="agent-research-worker").one()
        member.status = "paused"
        db.commit()
    finally:
        db.close()
    executor = build_machine_tool_executor(
        session_factory=security_client.factory,
        request=ExecutionRequest(
            org_id=security_client.org_id, workspace_id=security_client.workspace_id,
            task_id="task-research-worker", agent_id="agent-research-worker",
            data_class=DataClass.public, task_title="Research target company",
        ),
        execution_id=execution_id, attempt_id=attempt_id,
        worker_id="worker-research-worker", session_ttl_seconds=600,
    )
    with pytest.raises(ToolExecutionRejected):
        executor("os_revenue_lead_research_capture", _research_payload(), "sevt_paused_member")


def test_worker_custom_tool_executor_rechecks_revoked_workforce_capability(security_client):
    from app.integrations.runtime import ExecutionRequest
    from app.models import DataClass
    from app.workforce_models import WorkforceCapability
    from app.worker.tool_executor import build_machine_tool_executor, ToolExecutionRejected

    _agent_id, execution_id, _identity_id, attempt_id = _seed_worker_execution_and_identity(security_client)
    db = security_client.factory()
    try:
        grant = db.query(WorkforceCapability).filter_by(capability_key="public_lead_research").one()
        grant.enabled = False
        db.commit()
    finally:
        db.close()
    executor = build_machine_tool_executor(
        session_factory=security_client.factory,
        request=ExecutionRequest(
            org_id=security_client.org_id, workspace_id=security_client.workspace_id,
            task_id="task-research-worker", agent_id="agent-research-worker",
            data_class=DataClass.public, task_title="Research target company",
        ),
        execution_id=execution_id, attempt_id=attempt_id,
        worker_id="worker-research-worker", session_ttl_seconds=600,
    )
    with pytest.raises(ToolExecutionRejected):
        executor("os_revenue_lead_research_capture", _research_payload(), "sevt_revoked_grant")


def test_denied_tool_invocation_is_audited_without_raw_input(security_client):
    from app.models import AuditEvent

    _issued, session_id, headers = _issue_research_session(security_client)
    payload = _research_payload()
    payload["contact_email"] = "sensitive.owner@example.test"
    response = security_client.post(
        "/v1/machine/tools/revenue.lead.research.capture/invoke",
        headers={**headers, "Idempotency-Key": "revenue-research-denied-audit"},
        json={"session_id": session_id, "input": payload},
    )
    assert response.status_code == 422

    db = security_client.factory()
    try:
        event = (
            db.query(AuditEvent)
            .filter_by(
                org_id=security_client.org_id,
                event_type="tool.invocation.denied",
            )
            .order_by(AuditEvent.created_at.desc())
            .first()
        )
        assert event is not None
        assert event.payload["reason_code"] == "INPUT_SCHEMA_INVALID"
        assert "sensitive.owner@example.test" not in str(event.payload)
    finally:
        db.close()

def test_agent_tool_discovery_requires_an_active_workforce_capability(security_client):
    from app.machine_identity import issue_machine_credential
    from app.models import Agent, DataClass
    from app.security_models import MachineIdentity
    from app.workforce_models import WorkforceCapability, WorkforceMember

    now = datetime.now(timezone.utc)
    agent = Agent(
        id="agent-tool-discovery",
        org_id=security_client.org_id,
        workspace_id=security_client.workspace_id,
        name="Tool Discovery Agent",
        department="Business Development",
        instructions="Discover only explicitly granted OS tools.",
        runtime="claude_managed_agents",
        data_class=DataClass.public,
        enabled=True,
    )
    secret, token_hash, token_prefix = issue_machine_credential()
    identity = MachineIdentity(
        org_id=security_client.org_id,
        workspace_id=security_client.workspace_id,
        name="Tool Discovery Runtime",
        subject_type="agent",
        subject_id=agent.id,
        token_hash=token_hash,
        token_prefix=token_prefix,
        scopes=[
            "sessions:create",
            "tools:invoke",
            "tool:revenue.lead.research.capture",
        ],
        allowed_data_classes=["public"],
        expires_at=now + timedelta(days=1),
        created_by_user_id=security_client.founder.id,
    )
    db = security_client.factory()
    try:
        db.add_all([agent, identity])
        db.commit()
        headers = {"Authorization": f"Bearer aos_mi_{identity.id}.{secret}"}

        # Machine scopes alone must not advertise an agent tool. The call path
        # independently rechecks this same workforce capability before dispatch.
        hidden = security_client.get("/v1/machine/tools", headers=headers)
        assert hidden.status_code == 200
        assert hidden.json()["tools"] == []

        member = WorkforceMember(
            org_id=security_client.org_id,
            workspace_id=security_client.workspace_id,
            agent_id=agent.id,
            member_type="agent",
            name="Tool Discovery Agent",
            title="Lead Research Specialist",
            department_key="business_development_sales",
            responsibilities=["Capture public research"],
            autonomy_level=1,
            status="active",
            is_founder_reserved=False,
        )
        db.add(member)
        db.flush()
        db.add(WorkforceCapability(
            org_id=security_client.org_id,
            workspace_id=security_client.workspace_id,
            member_id=member.id,
            capability_key="public_lead_research",
            scope="workspace",
            allowed_data_classes=["public"],
            allowed_actions=["research.execute"],
            tool_allowlist=["revenue.lead.research.capture"],
            budget_minor=0,
            currency="INR",
            enabled=True,
        ))
        db.commit()

        visible = security_client.get("/v1/machine/tools", headers=headers)
        assert visible.status_code == 200
        assert [item["key"] for item in visible.json()["tools"]] == [
            "revenue.lead.research.capture"
        ]
        assert visible.json()["tools"][0]["allowed_data_classes"] == ["public"]
    finally:
        db.close()



def test_tool_discovery_hides_tools_that_require_unavailable_approval_adapter(
    security_client, monkeypatch
):
    from app.tool_registry import HealthReadInput, HealthReadOutput, ToolSpec
    import app.tool_gateway_routes as gateway_routes

    issued = _create_identity(
        security_client,
        scopes=[
            "sessions:create",
            "tools:invoke",
            "tool:approval.required",
        ],
        classes=["public"],
    )
    headers = {"Authorization": "Bearer " + issued["token"]}
    session = security_client.post(
        "/v1/machine/sessions",
        headers=headers,
        json={"purpose": "Inspect approved tool catalog", "data_class": "public", "ttl_seconds": 600},
    )
    assert session.status_code == 201, session.text

    approval_only_tool = ToolSpec(
        key="approval.required",
        provider_name="approval_required_tool",
        version="1.0.0",
        description="A tool requiring an approval adapter.",
        risk_level="high",
        allowed_data_classes=("public",),
        required_action="task.execute",
        minimum_scope="workspace",
        requires_approval=True,
        input_model=HealthReadInput,
        output_model=HealthReadOutput,
    )
    monkeypatch.setattr(gateway_routes, "list_tools", lambda: [approval_only_tool])

    response = security_client.get("/v1/machine/tools", headers=headers)
    assert response.status_code == 200
    assert response.json()["tools"] == []

def test_tool_gateway_enforces_machine_scope_allowlist_default_limit_and_idempotent_replay(
    security_client, monkeypatch,
):
    from fastapi import HTTPException
    from app.machine_identity import authenticate_machine_token, create_agent_session
    from app.tool_gateway import invoke_registered_tool
    import app.tool_gateway as gateway

    monkeypatch.setattr(gateway, "DEFAULT_MAX_TOOL_CALLS_PER_SESSION", 1)

    issued = _create_identity(
        security_client,
        scopes=[
            "sessions:create",
            "tools:invoke",
            "tool:system.health.read",
        ],
        classes=["public"],
    )
    db = security_client.factory()
    try:
        principal = authenticate_machine_token(
            "Bearer " + issued["token"], db
        )
        session = create_agent_session(
            db,
            principal,
            purpose="Bounded tool session",
            data_class="public",
            ttl_seconds=600,
        )
        db.commit()

        first = invoke_registered_tool(
            db,
            principal,
            session_id=session.id,
            tool_key="system.health.read",
            payload={},
            idempotency_key="health-session-call-01",
        )
        assert first["status"] == "succeeded"

        replay = invoke_registered_tool(
            db,
            principal,
            session_id=session.id,
            tool_key="system.health.read",
            payload={},
            idempotency_key="health-session-call-01",
        )
        assert replay["replayed"] is True

        with pytest.raises(HTTPException) as limited:
            invoke_registered_tool(
                db,
                principal,
                session_id=session.id,
                tool_key="system.health.read",
                payload={},
                idempotency_key="health-session-call-02",
            )
        assert limited.value.status_code == 429

        with pytest.raises(HTTPException) as disallowed:
            invoke_registered_tool(
                db,
                principal,
                session_id=session.id,
                tool_key="revenue.lead.research.capture",
                payload={},
                idempotency_key="health-session-call-03",
            )
        assert disallowed.value.status_code == 403
    finally:
        db.close()



def test_session_credential_is_bound_to_one_active_agent_session_and_hash_only(security_client):
    from app.session_credentials import issue_session_credential
    from app.security_models import MachineSessionCredential

    issued = _create_identity(security_client)
    db = security_client.factory()
    try:
        principal = authenticate_machine_token("Bearer " + issued["token"], db)
        session = create_agent_session(
            db, principal, purpose="Claude MCP session", data_class="public", ttl_seconds=600
        )
        db.commit()
        credential = issue_session_credential(
            db, principal, session_id=session.id, ttl_seconds=300
        )
        assert credential.token.startswith("aos_ms_")
        row = db.query(MachineSessionCredential).filter_by(id=credential.credential_id).one()
        assert credential.token.rsplit(".", 1)[1] not in row.token_hash
        assert row.session_id == session.id
        assert row.machine_identity_id == principal.identity.id
        from app.session_credentials import _utc
        assert _utc(row.expires_at) <= _utc(session.expires_at)
    finally:
        db.close()


def test_session_credential_authentication_rejects_wrong_token_and_revoked_session(security_client):
    from app.session_credentials import issue_session_credential, authenticate_session_credential

    issued = _create_identity(security_client)
    db = security_client.factory()
    try:
        principal = authenticate_machine_token("Bearer " + issued["token"], db)
        session = create_agent_session(
            db, principal, purpose="Claude MCP session", data_class="public", ttl_seconds=600
        )
        db.commit()
        credential = issue_session_credential(
            db, principal, session_id=session.id, ttl_seconds=300
        )
        context = authenticate_session_credential(
            db, "Bearer " + credential.token
        )
        assert context.session_id == session.id
        assert context.machine_identity_id == principal.identity.id
        from app.session_credentials import load_active_session_context
        reloaded_principal, reloaded_session = load_active_session_context(db, context)
        assert reloaded_principal.identity.id == principal.identity.id
        assert reloaded_session.id == session.id
        with pytest.raises(Exception):
            authenticate_session_credential(
                db, "Bearer " + credential.token[:-1] + "x"
            )
        session.status = "cancelled"
        db.commit()
        with pytest.raises(Exception):
            authenticate_session_credential(db, "Bearer " + credential.token)
    finally:
        db.close()


def test_machine_identity_can_mint_one_short_lived_mcp_credential_for_its_own_session(security_client):
    issued, session_id, headers = _issue_tool_session(security_client, subject_type="service")
    response = security_client.post(
        f"/v1/machine/sessions/{session_id}/mcp-credential",
        headers=headers,
        json={"ttl_seconds": 300},
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["session_id"] == session_id
    assert payload["token"].startswith("aos_ms_")
    assert payload["credential_version"] == 1
    assert "shown once" in payload["warning"]

    from app.session_credentials import authenticate_session_credential
    from app.security_models import MachineSessionCredential
    db = security_client.factory()
    try:
        context = authenticate_session_credential(
            db, "Bearer " + payload["token"], requests_per_minute=10
        )
        assert context.session_id == session_id
        assert context.machine_identity_id == issued["id"]
        credential = db.get(MachineSessionCredential, payload["credential_id"])
        assert credential is not None
        assert credential.token_hash != payload["token"]
        assert len(credential.token_hash) == 64
    finally:
        db.close()


def test_machine_identity_without_session_creation_scope_cannot_mint_mcp_credential(security_client):
    issued = _create_identity(
        security_client, scopes=["tools:invoke", "tool:system.health.read"]
    )
    headers = {"Authorization": "Bearer " + issued["token"]}
    session = security_client.post(
        "/v1/machine/sessions",
        headers=headers,
        json={"purpose": "Read health", "data_class": "public", "ttl_seconds": 300},
    )
    assert session.status_code == 403


def test_workspace_knowledge_search_returns_only_approved_public_workspace_wide_items(security_client):
    from app.private_ops_models import KnowledgeItem
    from app.tool_registry import get_tool, validate_tool_input, validate_tool_output, execute_tool

    db = security_client.factory()
    try:
        other_workspace = Workspace(
            id="security-ws-other", org_id=security_client.org_id, name="Other Workspace"
        )
        db.add(other_workspace)
        db.flush()
        db.add_all([
            KnowledgeItem(
                org_id=security_client.org_id, workspace_id=security_client.workspace_id,
                key="public.playbook", version=1, title="Public agency playbook",
                content="Approved public guidance for project delivery.",
                source_type="policy", source_reference="founder-approved-public-policy",
                classification="public", status="approved", owner_user_id=security_client.founder.id,
                created_by=security_client.founder.id, approved_by=security_client.founder.id,
                approved_at=datetime.now(timezone.utc),
            ),
            KnowledgeItem(
                org_id=security_client.org_id, workspace_id=security_client.workspace_id,
                key="public.playbook", version=2, title="Updated public agency playbook",
                content="Latest approved public guidance for project delivery.",
                source_type="policy", source_reference="founder-approved-public-policy-v2",
                classification="public", status="approved", owner_user_id=security_client.founder.id,
                created_by=security_client.founder.id, approved_by=security_client.founder.id,
                approved_at=datetime.now(timezone.utc),
            ),
            KnowledgeItem(
                org_id=security_client.org_id, workspace_id=security_client.workspace_id,
                key="internal.playbook", version=1, title="Internal agency playbook",
                content="Internal-only delivery notes.", source_type="policy",
                source_reference="internal-policy", classification="internal", status="approved",
                owner_user_id=security_client.founder.id, created_by=security_client.founder.id,
                approved_by=security_client.founder.id, approved_at=datetime.now(timezone.utc),
            ),
            KnowledgeItem(
                org_id=security_client.org_id, workspace_id=other_workspace.id,
                key="public.playbook", version=1, title="Other workspace playbook",
                content="Must never cross workspace boundaries.", source_type="policy",
                source_reference="other-workspace-policy", classification="public", status="approved",
                owner_user_id=security_client.founder.id, created_by=security_client.founder.id,
                approved_by=security_client.founder.id, approved_at=datetime.now(timezone.utc),
            ),
            KnowledgeItem(
                org_id=security_client.org_id, workspace_id=security_client.workspace_id,
                key="draft.playbook", version=1, title="Draft public playbook",
                content="Not approved and must not be exposed.", source_type="policy",
                source_reference="draft-policy", classification="public", status="draft",
                owner_user_id=security_client.founder.id, created_by=security_client.founder.id,
            ),
        ])
        db.commit()
        spec = get_tool("workspace.knowledge.search")
        assert spec is not None
        identity = MachineIdentity(
            org_id=security_client.org_id, workspace_id=security_client.workspace_id,
            name="Cowork Read Context", subject_type="service", subject_id="cowork",
            token_hash="0" * 64, token_prefix="test", scopes=[],
            allowed_data_classes=["public"],
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            created_by_user_id=security_client.founder.id,
        )
        result = execute_tool(
            db, spec, validate_tool_input(spec, {"query": "playbook", "limit": 10}),
            identity=identity, idempotency_key="knowledge-search-0001",
        )
        validated = validate_tool_output(spec, result)
        assert [item["key"] for item in validated["items"]] == ["public.playbook"]
        assert validated["items"][0]["version"] == 2
        assert validated["items"][0]["title"] == "Updated public agency playbook"
    finally:
        db.close()


def test_workspace_knowledge_search_requires_a_query_or_exact_key(security_client):
    from app.tool_registry import get_tool, validate_tool_input
    with pytest.raises(Exception):
        validate_tool_input(get_tool("workspace.knowledge.search"), {"limit": 10})


def test_machine_identity_cannot_mint_mcp_credential_for_another_identity_session(security_client):
    _first_identity, _first_session, _first_headers = _issue_tool_session(security_client, subject_type="service")
    second_identity, second_session, second_headers = _issue_tool_session(security_client, subject_type="service")
    response = security_client.post(
        f"/v1/machine/sessions/{second_session}/mcp-credential",
        headers=_first_headers,
        json={"ttl_seconds": 300},
    )
    assert response.status_code == 403


def test_machine_identity_can_revoke_its_session_and_all_session_credentials(security_client):
    _identity, session_id, headers = _issue_tool_session(security_client, subject_type="service")
    issued = security_client.post(
        f"/v1/machine/sessions/{session_id}/mcp-credential",
        headers=headers, json={"ttl_seconds": 300},
    )
    assert issued.status_code == 201, issued.text

    revoked = security_client.post(
        f"/v1/machine/sessions/{session_id}/revoke", headers=headers
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["revoked"] is True
    assert revoked.json()["credentials_revoked"] == 1

    from app.session_credentials import authenticate_session_credential
    db = security_client.factory()
    try:
        with pytest.raises(Exception):
            authenticate_session_credential(db, "Bearer " + issued.json()["token"])
    finally:
        db.close()


def test_machine_identity_cannot_revoke_another_identity_session(security_client):
    _first_identity, _first_session, first_headers = _issue_tool_session(security_client, subject_type="service")
    _second_identity, second_session, _second_headers = _issue_tool_session(security_client, subject_type="service")
    response = security_client.post(
        f"/v1/machine/sessions/{second_session}/revoke", headers=first_headers
    )
    assert response.status_code == 404


def test_service_machine_bearer_is_bound_to_its_active_mcp_session_path(security_client):
    from app.mcp_server import authenticate_machine_session, load_mcp_session_context
    issued, session_id, headers = _issue_tool_session(
        security_client, subject_type="service"
    )
    db = security_client.factory()
    try:
        context = authenticate_machine_session(
            db, headers["Authorization"], session_id
        )
        assert context.machine_identity_id == issued["id"]
        assert context.session_id == session_id
        loaded_principal, loaded_session = load_mcp_session_context(db, context)
        assert loaded_principal.identity.id == issued["id"]
        assert loaded_session.id == session_id

        with pytest.raises(Exception):
            authenticate_machine_session(
                db, headers["Authorization"], "00000000-0000-0000-0000-000000000000"
            )
    finally:
        db.close()
