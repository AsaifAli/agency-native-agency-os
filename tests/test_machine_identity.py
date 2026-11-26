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
    client.org_id, client.workspace_id, client.founder = org.id, workspace.id, founder
    client.factory = factory
    client.set_principal = lambda selected_user: principal.update(user=selected_user)
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
