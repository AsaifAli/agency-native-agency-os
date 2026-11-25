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
    app.include_router(revenue_research_router)
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
        db.add(Membership(org_id=security_client.org_id, user_id=operator.id, role=Role.operator)); db.commit()
    finally:
        db.close()
    security_client.app.dependency_overrides[get_principal] = lambda: Principal(user=operator)
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


def test_session_credential_is_hash_only_and_authenticates_one_session(security_client):
    from app.machine_identity import authenticate_machine_token
    from app.session_credentials import issue_session_credential, authenticate_session_credential
    from app.security_models import MachineSessionCredential

    issued, session_id, _headers = _issue_tool_session(security_client)
    db = security_client.factory()
    try:
        principal = authenticate_machine_token("Bearer " + issued["token"], db)
        credential = issue_session_credential(
            db, principal, session_id=session_id, ttl_seconds=300
        )
        assert credential.token.startswith("aos_ms_")
        raw_secret = credential.token.split(".", 1)[1]
        stored = db.get(MachineSessionCredential, credential.credential_id)
        assert stored is not None
        assert stored.token_hash != raw_secret
        assert len(stored.token_hash) == 64
        assert stored.token_prefix == f"aos_ms_{credential.credential_id}."
        assert not hasattr(stored, "token")

        context = authenticate_session_credential(
            db, "Bearer " + credential.token, requests_per_minute=120
        )
        assert context.session_id == session_id
        assert context.machine_identity_id == issued["id"]
        db.refresh(stored)
        assert stored.request_count_window == 1
        assert stored.last_used_at is not None
    finally:
        db.close()


def test_session_credential_rotation_revokes_previous_token(security_client):
    from app.machine_identity import authenticate_machine_token
    from app.session_credentials import issue_session_credential, authenticate_session_credential
    from app.security_models import MachineSessionCredential

    issued, session_id, _headers = _issue_tool_session(security_client)
    db = security_client.factory()
    try:
        principal = authenticate_machine_token("Bearer " + issued["token"], db)
        first = issue_session_credential(db, principal, session_id=session_id, ttl_seconds=300)
        second = issue_session_credential(db, principal, session_id=session_id, ttl_seconds=300)
        old = db.get(MachineSessionCredential, first.credential_id)
        current = db.get(MachineSessionCredential, second.credential_id)
        assert old.revoked_at is not None
        assert old.revocation_reason == "CREDENTIAL_ROTATED"
        assert current.revoked_at is None
        assert second.credential_version == first.credential_version + 1
        with pytest.raises(HTTPException) as exc:
            authenticate_session_credential(db, "Bearer " + first.token)
        assert exc.value.status_code == 401
        assert authenticate_session_credential(db, "Bearer " + second.token).session_id == session_id
    finally:
        db.close()


def test_session_credential_rate_limit_is_durable(security_client):
    from app.machine_identity import authenticate_machine_token
    from app.session_credentials import issue_session_credential, authenticate_session_credential

    issued, session_id, _headers = _issue_tool_session(security_client)
    now = datetime.now(timezone.utc)
    db = security_client.factory()
    try:
        principal = authenticate_machine_token("Bearer " + issued["token"], db)
        credential = issue_session_credential(
            db, principal, session_id=session_id, ttl_seconds=300, now=now
        )
        authenticate_session_credential(
            db, "Bearer " + credential.token, requests_per_minute=1, now=now
        )
        with pytest.raises(HTTPException) as exc:
            authenticate_session_credential(
                db,
                "Bearer " + credential.token,
                requests_per_minute=1,
                now=now + timedelta(seconds=1),
            )
        assert exc.value.status_code == 429
    finally:
        db.close()


def test_session_credential_expiry_and_session_closure_revoke_access(security_client):
    from app.machine_identity import authenticate_machine_token
    from app.session_credentials import issue_session_credential, authenticate_session_credential, close_agent_session
    from app.security_models import MachineSessionCredential

    issued, session_id, _headers = _issue_tool_session(security_client)
    db = security_client.factory()
    try:
        principal = authenticate_machine_token("Bearer " + issued["token"], db)
        credential = issue_session_credential(db, principal, session_id=session_id, ttl_seconds=300)
        closed = close_agent_session(
            db, principal, session_id=session_id, status="closed", reason_code="TEST_SESSION_CLOSE"
        )
        assert closed.status == "closed"
        stored = db.get(MachineSessionCredential, credential.credential_id)
        assert stored.revoked_at is not None
        with pytest.raises(HTTPException) as exc:
            authenticate_session_credential(db, "Bearer " + credential.token)
        assert exc.value.status_code == 401
    finally:
        db.close()


def test_identity_revocation_revokes_provider_vault_credential_reference(security_client):
    from app.machine_identity import authenticate_machine_token
    from app.session_credentials import issue_session_credential
    from app.security_models import MachineSessionCredential

    issued, session_id, _headers = _issue_tool_session(security_client)
    db = security_client.factory()
    try:
        principal = authenticate_machine_token("Bearer " + issued["token"], db)
        credential = issue_session_credential(db, principal, session_id=session_id, ttl_seconds=300)
        stored = db.get(MachineSessionCredential, credential.credential_id)
        stored.provider_vault_id = "vault_test"
        stored.provider_credential_id = "credential_test"
        stored.provider_credential_status = "active"
        db.commit()
    finally:
        db.close()

    response = security_client.post(
        f"/v1/orgs/{security_client.org_id}/machine-identities/{issued['id']}/revoke"
    )
    assert response.status_code == 200, response.text
    db = security_client.factory()
    try:
        stored = db.get(MachineSessionCredential, credential.credential_id)
        assert stored.revoked_at is not None
        assert stored.provider_credential_status == "delete_pending"
    finally:
        db.close()


def test_machine_session_route_returns_one_time_mcp_token_only_when_enabled(security_client, monkeypatch):
    from app.config import settings
    from app.security_models import MachineSessionCredential

    issued = _create_identity(security_client, scopes=["sessions:create"], classes=["public"])
    monkeypatch.setattr(settings, "mcp_gateway_enabled", True)
    monkeypatch.setattr(settings, "mcp_public_url", "https://api.example.test/mcp/agency-os")
    monkeypatch.setattr(settings, "mcp_session_token_ttl_seconds", 300)
    response = security_client.post(
        "/v1/machine/sessions",
        headers={"Authorization": "Bearer " + issued["token"]},
        json={"purpose": "Public MCP session", "data_class": "public", "ttl_seconds": 600},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["mcp_token"].startswith("aos_ms_")
    assert body["mcp_server_url"] == settings.mcp_public_url
    db = security_client.factory()
    try:
        credential = db.query(MachineSessionCredential).filter_by(session_id=body["id"]).one()
        assert body["mcp_token"].split(".", 1)[1] not in credential.token_hash
        assert credential.token_prefix == f"aos_ms_{credential.id}."
    finally:
        db.close()


def test_founder_close_session_route_revokes_mcp_token(security_client):
    from app.machine_identity import authenticate_machine_token
    from app.session_credentials import issue_session_credential, authenticate_session_credential

    issued, session_id, _headers = _issue_tool_session(security_client)
    db = security_client.factory()
    try:
        principal = authenticate_machine_token("Bearer " + issued["token"], db)
        credential = issue_session_credential(db, principal, session_id=session_id, ttl_seconds=300)
    finally:
        db.close()
    response = security_client.post(
        f"/v1/orgs/{security_client.org_id}/workspaces/{security_client.workspace_id}/machine-sessions/{session_id}/close"
    )
    assert response.status_code == 200, response.text
    db = security_client.factory()
    try:
        with pytest.raises(HTTPException):
            authenticate_session_credential(db, "Bearer " + credential.token)
    finally:
        db.close()
