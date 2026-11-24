import pytest
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import Principal, get_principal
from app.db import Base, get_db
from app.models import (
    Approval, ApprovalStatus, FounderAuthority, Membership, Organization,
    Role, User, Workspace, Task,
)
from app.domain_models import Project
from app.operations_models import ServicePlaybook, ScopeChangeRequest, TimeEntry, ProjectCost
from app.operations_routes import router
from app.telephony.models import OutboxEvent


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    db = TestingSession()
    user = User(email="founder-ops@example.test", display_name="Founder")
    org = Organization(name="Operations Test Org")
    other_org = Organization(name="Other Org")
    db.add_all([user, org, other_org])
    db.flush()
    ws = Workspace(id="ops-ws", org_id=org.id, name="Workspace")
    other_ws = Workspace(id="ops-other-ws", org_id=other_org.id, name="Other")
    db.add_all([ws, other_ws])
    db.add_all([
        Membership(org_id=org.id, user_id=user.id, role=Role.owner),
        FounderAuthority(org_id=org.id, user_id=user.id, grant_source="test"),
    ])
    project = Project(
        org_id=org.id, workspace_id=ws.id, name="Build AI workflow",
        budget_minor=500000, contract_value_minor=1200000,
        estimated_hours=80, currency="INR", owner_user_id=user.id,
        due_date=datetime(2027, 1, 31, tzinfo=timezone.utc),
    )
    db.add(project)
    db.commit()

    app = FastAPI()
    app.include_router(router)

    def override_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_principal] = lambda: Principal(user=user)
    tc = TestClient(app)
    tc.org_id, tc.ws_id, tc.other_ws_id, tc.user_id, tc.project_id = org.id, ws.id, other_ws.id, user.id, project.id
    tc.session_factory = TestingSession
    yield tc
    db.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def headers():
    return {"Authorization": "Bearer test"}


def test_playbook_create_and_founder_activation(client):
    org, ws = client.org_id, client.ws_id
    created = client.post(f"/v1/orgs/{org}/operations/playbooks", headers=headers(), json={
        "workspace_id": ws, "title": "Enterprise RAG delivery",
        "service_line": "custom_ai_applications",
        "required_inputs": ["sample documents", "identity requirements"],
        "deliverables": ["retrieval API", "evaluation report"],
        "acceptance_criteria": ["citations verified", "tenant isolation tested"],
        "security_checks": ["PII review", "access control tests"],
    })
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "draft"
    activated = client.patch(
        f"/v1/orgs/{org}/operations/playbooks/{created.json()['id']}/status",
        headers=headers(), json={"status": "active"},
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["version"] == 2


def test_time_and_cost_roll_up_to_project_financial_summary(client):
    org, ws, project = client.org_id, client.ws_id, client.project_id
    t = client.post(f"/v1/orgs/{org}/operations/time-entries", headers=headers(), json={
        "workspace_id": ws, "project_id": project, "description": "Implement retrieval pipeline",
        "duration_minutes": 120, "billable": True, "hourly_cost_minor": 30000,
        "started_at": "2026-11-24T09:00:00Z",
    })
    assert t.status_code == 201, t.text
    c = client.post(f"/v1/orgs/{org}/operations/project-costs", headers=headers(), json={
        "workspace_id": ws, "project_id": project, "category": "cloud",
        "description": "Development environment", "amount_minor": 50000,
        "currency": "INR", "incurred_at": "2026-11-24T10:00:00Z",
    })
    assert c.status_code == 201, c.text
    summary = client.get(
        f"/v1/orgs/{org}/operations/projects/{project}/financial-summary",
        params={"workspace_id": ws}, headers=headers(),
    )
    assert summary.status_code == 200, summary.text
    data = summary.json()
    assert data["actual_minutes"] == 120
    assert data["labor_cost_minor"] == 60000
    assert data["other_cost_minor"] == 50000
    assert data["actual_cost_minor"] == 110000
    assert data["gross_margin_minor"] == 1090000
    assert data["budget_remaining_minor"] == 390000
    assert data["margin_is_provisional"] is True


def test_scope_change_requires_single_use_founder_approval(client):
    org, ws, project = client.org_id, client.ws_id, client.project_id
    change = client.post(f"/v1/orgs/{org}/operations/scope-changes", headers=headers(), json={
        "workspace_id": ws, "project_id": project, "title": "Add a second data source",
        "description": "Include another internal repository",
        "impact_summary": "Additional connector and regression coverage",
        "estimated_hours_delta": 12, "budget_delta_minor": 40000,
        "contract_value_delta_minor": 90000, "schedule_days_delta": 5,
    })
    assert change.status_code == 201, change.text
    change_id = change.json()["id"]

    # No approval means no commercial or schedule mutation.
    denied = client.post(
        f"/v1/orgs/{org}/operations/scope-changes/{change_id}/approve",
        headers=headers(), json={"approval_id": "missing-approval"},
    )
    assert denied.status_code == 403

    from app.db import get_db as db_dependency
    session_gen = client.app.dependency_overrides[db_dependency]()
    db = next(session_gen)
    try:
        approval = Approval(
            org_id=org, workspace_id=ws, action_type="scope.change.accept",
            resource_id=change_id, idempotency_key="scope-approval-1",
            request_payload={"reason": "Founder-approved scope change"},
            status=ApprovalStatus.approved, requested_by=client.user_id,
            decided_by=client.user_id, decision_note="Approved",
            decided_at=datetime.now(timezone.utc),
        )
        db.add(approval)
        db.commit()
        approval_id = approval.id
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass

    accepted = client.post(
        f"/v1/orgs/{org}/operations/scope-changes/{change_id}/approve",
        headers=headers(), json={"approval_id": approval_id},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "approved"

    again = client.post(
        f"/v1/orgs/{org}/operations/scope-changes/{change_id}/approve",
        headers=headers(), json={"approval_id": approval_id},
    )
    assert again.status_code == 409


def test_project_currency_must_match_cost_currency(client):
    r = client.post(f"/v1/orgs/{client.org_id}/operations/project-costs", headers=headers(), json={
        "workspace_id": client.ws_id, "project_id": client.project_id,
        "category": "cloud", "description": "Cloud bill", "amount_minor": 100,
        "currency": "USD", "incurred_at": "2026-11-24T10:00:00Z",
    })
    assert r.status_code == 422


def test_cross_workspace_project_is_not_visible(client):
    r = client.get(
        f"/v1/orgs/{client.org_id}/operations/projects/{client.project_id}/financial-summary",
        params={"workspace_id": client.other_ws_id}, headers=headers(),
    )
    assert r.status_code == 404



def test_founder_exception_inbox_surfaces_pending_approvals_and_blocked_tasks(client):
    db = client.session_factory()
    try:
        db.add(Approval(
            org_id=client.org_id, workspace_id=client.ws_id,
            action_type="pricing.change", resource_id="quote-1",
            idempotency_key="pending-pricing-approval",
            request_payload={"reason": "Price review"},
            status=ApprovalStatus.pending, requested_by=client.user_id,
        ))
        db.add(Task(
            org_id=client.org_id, workspace_id=client.ws_id,
            title="Resolve provider failure", status="blocked",
            created_by=client.user_id,
        ))
        db.commit()
    finally:
        db.close()
    r = client.get(
        f"/v1/orgs/{client.org_id}/operations/exceptions",
        params={"workspace_id": client.ws_id}, headers=headers(),
    )
    assert r.status_code == 200, r.text
    kinds = {item["kind"] for item in r.json()["items"]}
    assert {"approval", "blocked_task"} <= kinds


def test_agent_performance_is_workspace_scoped(client):
    r = client.get(
        f"/v1/orgs/{client.org_id}/operations/agent-performance",
        params={"workspace_id": client.ws_id}, headers=headers(),
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"items": []}

def test_outbox_health_is_founder_only_and_org_scoped(client):
    db = client.session_factory()
    try:
        db.add_all([
            OutboxEvent(
                org_id=client.org_id,
                workspace_id=client.ws_id,
                event_type="test.pending",
                schema_version=1,
                aggregate_type="test",
                aggregate_id="pending-1",
                idempotency_key="health-pending-1",
                payload={"must_not_be_exposed": True},
                status="pending",
                attempts=0,
            ),
            OutboxEvent(
                org_id=client.org_id,
                workspace_id=client.ws_id,
                event_type="test.retry",
                schema_version=1,
                aggregate_type="test",
                aggregate_id="retry-1",
                idempotency_key="health-retry-1",
                payload={},
                status="pending",
                attempts=2,
            ),
            OutboxEvent(
                org_id=client.org_id,
                workspace_id=client.ws_id,
                event_type="test.dead",
                schema_version=1,
                aggregate_type="test",
                aggregate_id="dead-1",
                idempotency_key="health-dead-1",
                payload={},
                status="dead_letter",
                attempts=8,
            ),
            OutboxEvent(
                org_id=client.other_ws_id,
                workspace_id=client.other_ws_id,
                event_type="test.other",
                schema_version=1,
                aggregate_type="test",
                aggregate_id="other-1",
                idempotency_key="health-other-1",
                payload={},
                status="dead_letter",
                attempts=8,
            ),
        ])
        db.commit()
    finally:
        db.close()

    response = client.get(
        f"/v1/orgs/{client.org_id}/operations/outbox-health",
        headers=headers(),
    )

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["pending_count"] == 2
    assert data["retrying_count"] == 1
    assert data["dead_letter_count"] == 1
    assert "payload" not in data
    assert "idempotency_key" not in data
    assert "worker_id" not in data

def test_outbox_health_denies_member_without_founder_authority(client):
    db = client.session_factory()
    try:
        member = User(
            email="ordinary-member@example.test",
            display_name="Ordinary Member",
        )
        db.add(member)
        db.flush()

        db.add(Membership(
            org_id=client.org_id,
            user_id=member.id,
            role=Role.operator,
        ))
        db.commit()

        client.app.dependency_overrides[get_principal] = (
            lambda: Principal(user=member)
        )

        response = client.get(
            f"/v1/orgs/{client.org_id}/operations/outbox-health",
            headers=headers(),
        )

        assert response.status_code == 403
    finally:
        client.app.dependency_overrides.pop(get_principal, None)
        db.close()