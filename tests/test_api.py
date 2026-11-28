import os
import uuid
os.environ["DATABASE_URL"] = "sqlite:///./test_agency_os.db"
os.environ["DEV_AUTH_ENABLED"] = "true"
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, engine, SessionLocal
from app.models import (
    User, Organization, Membership, Workspace, Role,
    Agent, Task, DataClass, AuditEvent, Execution, ExecutionStatus, WorkspaceGrant,
    FounderAuthority,
)
from app.telephony.models import OutboxEvent
from app.config import settings
from app.worker.processor import process_one_execution

def setup_module():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    user = User(email="owner@test.local", display_name="Owner")
    org = Organization(name="Test Org")
    db.add_all([user, org]); db.flush()
    db.add(Membership(org_id=org.id, user_id=user.id, role=Role.owner))
    db.add(Workspace(id="ws-test", org_id=org.id, name="Test Workspace", created_by=user.id))
    db.flush()
    db.add(WorkspaceGrant(
        org_id=org.id, workspace_id="ws-test", user_id=user.id, granted_by=user.id,
    ))
    db.commit()
    db.close()

def test_tenant_scoped_workspace_list():
    client = TestClient(app)
    response = client.get("/v1/orgs/" + _org_id() + "/workspaces",
                          headers={"Authorization": "Bearer dev:owner@test.local"})
    assert response.status_code == 200
    assert response.json()[0]["id"] == "ws-test"

def _org_id():
    db = SessionLocal()
    try:
        return db.query(Organization).filter_by(name="Test Org").one().id
    finally:
        db.close()



def _seed_execution_records(runtime):
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(email="owner@test.local").one()
        org = db.query(Organization).filter_by(name="Test Org").one()
        workspace = db.query(Workspace).filter_by(id="ws-test").one()
        suffix = uuid.uuid4().hex[:10]
        agent = Agent(
            org_id=org.id,
            workspace_id=workspace.id,
            name=f"API execution test agent {suffix}",
            runtime=runtime,
            data_class=DataClass.synthetic,
            enabled=True,
        )
        task = Task(
            org_id=org.id,
            workspace_id=workspace.id,
            title=f"API execution test task {suffix}",
            description="Synthetic API test",
            created_by=user.id,
        )
        db.add_all([agent, task])
        db.commit()
        return org.id, workspace.id, task.id, agent.id
    finally:
        db.close()


def test_execution_api_rejects_unconfigured_runtime(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "mock_runtime_enabled", False)
    org_id, workspace_id, task_id, agent_id = _seed_execution_records(
        "claude_managed_agents"
    )

    client = TestClient(app)
    response = client.post(
        f"/v1/orgs/{org_id}/executions",
        headers={"Authorization": "Bearer dev:owner@test.local"},
        json={
            "workspace_id": workspace_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "idempotency_key": f"api-runtime-disabled-{uuid.uuid4().hex}",
        },
    )

    assert response.status_code == 403
    assert "not configured" in response.json()["detail"]


def test_execution_api_accepts_explicit_development_mock(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "mock_runtime_enabled", True)
    org_id, workspace_id, task_id, agent_id = _seed_execution_records("mock")

    client = TestClient(app)
    response = client.post(
        f"/v1/orgs/{org_id}/executions",
        headers={"Authorization": "Bearer dev:owner@test.local"},
        json={
            "workspace_id": workspace_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "idempotency_key": f"api-runtime-enabled-{uuid.uuid4().hex}",
        },
    )

    assert response.status_code == 201
    assert response.json()["runtime"] == "mock"
    assert response.json()["status"] == "queued"

    execution_id = response.json()["id"]
    processed_id = process_one_execution(
        worker_id="api-e2e-test-worker",
        session_factory=SessionLocal,
    )
    assert processed_id == execution_id

    db = SessionLocal()
    try:
        saved = db.get(Execution, execution_id)
        assert saved.status == ExecutionStatus.succeeded, (
            "Mock execution did not succeed: "
            f"status={saved.status!r}, runtime={saved.runtime!r}, "
            f"error_code={saved.error_code!r}, "
            f"error_message={saved.error_message!r}, "
            f"attempt_count={saved.attempt_count!r}"
        )
        assert saved.result["provider"] == "mock"
        assert saved.result["status"] == "succeeded"

        event_types = {
            event.event_type
            for event in db.query(AuditEvent)
            .filter_by(resource_type="execution", resource_id=execution_id)
            .all()
        }
        assert "execution.queued" in event_types
        assert "execution.succeeded" in event_types
    finally:
        db.close()



def test_execution_history_and_trace_are_workspace_scoped(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "mock_runtime_enabled", True)
    org_id, workspace_id, task_id, agent_id = _seed_execution_records("mock")
    client = TestClient(app)
    headers = {"Authorization": "Bearer dev:owner@test.local"}
    created = client.post(
        f"/v1/orgs/{org_id}/executions",
        headers=headers,
        json={
            "workspace_id": workspace_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "idempotency_key": f"history-trace-{uuid.uuid4().hex}",
        },
    )
    assert created.status_code == 201
    execution_id = created.json()["id"]

    listed = client.get(
        f"/v1/orgs/{org_id}/executions",
        params={"workspace_id": workspace_id},
        headers=headers,
    )
    assert listed.status_code == 200
    assert any(row["id"] == execution_id for row in listed.json())

    processed_id = process_one_execution(
        worker_id="history-trace-worker",
        session_factory=SessionLocal,
    )
    assert processed_id == execution_id

    trace = client.get(
        f"/v1/orgs/{org_id}/executions/{execution_id}/trace",
        params={"workspace_id": workspace_id},
        headers=headers,
    )
    assert trace.status_code == 200
    event_types = {row["event_type"] for row in trace.json()}
    assert {"execution.queued", "execution.claimed", "execution.started",
            "execution.succeeded"}.issubset(event_types)

    wrong_workspace = client.get(
        f"/v1/orgs/{org_id}/executions/{execution_id}/trace",
        params={"workspace_id": "not-this-workspace"},
        headers=headers,
    )
    assert wrong_workspace.status_code == 404


def test_execution_history_rejects_invalid_status_and_limit():
    client = TestClient(app)
    headers = {"Authorization": "Bearer dev:owner@test.local"}
    org_id = _org_id()
    invalid_status = client.get(
        f"/v1/orgs/{org_id}/executions",
        params={"workspace_id": "ws-test", "status": "unknown"},
        headers=headers,
    )
    assert invalid_status.status_code == 422
    invalid_limit = client.get(
        f"/v1/orgs/{org_id}/executions",
        params={"workspace_id": "ws-test", "limit": 501},
        headers=headers,
    )
    assert invalid_limit.status_code == 422


def test_development_token_endpoint_remains_usable_without_browser_session():
    client = TestClient(app)
    issued = client.post("/v1/auth/dev-token", params={"email": "owner@test.local"})
    assert issued.status_code == 200
    token = issued.json()["access_token"]
    identity = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert identity.status_code == 200
    assert identity.json()["email"] == "owner@test.local"


def test_new_workspace_is_granted_to_creator_but_not_future_org_members():
    client = TestClient(app)
    headers = {"Authorization": "Bearer dev:owner@test.local"}
    org_id = _org_id()
    created = client.post(
        f"/v1/orgs/{org_id}/workspaces",
        headers=headers,
        json={"name": "Explicit grant test workspace"},
    )
    assert created.status_code == 201
    workspace_id = created.json()["id"]

    owner_workspaces = client.get(
        f"/v1/orgs/{org_id}/workspaces", headers=headers
    )
    assert owner_workspaces.status_code == 200
    assert workspace_id in {row["id"] for row in owner_workspaces.json()}

    db = SessionLocal()
    try:
        viewer = User(email=f"workspace-viewer-{uuid.uuid4().hex}@test.local")
        db.add(viewer)
        db.flush()
        db.add(Membership(org_id=org_id, user_id=viewer.id, role=Role.viewer))
        db.commit()
        viewer_email = viewer.email
    finally:
        db.close()

    viewer_headers = {"Authorization": f"Bearer dev:{viewer_email}"}
    viewer_workspaces = client.get(
        f"/v1/orgs/{org_id}/workspaces", headers=viewer_headers
    )
    assert viewer_workspaces.status_code == 200
    assert workspace_id not in {row["id"] for row in viewer_workspaces.json()}

    denied = client.get(
        f"/v1/orgs/{org_id}/agents",
        params={"workspace_id": workspace_id},
        headers=viewer_headers,
    )
    assert denied.status_code == 404


def test_organization_owner_without_founder_authority_cannot_change_workspace_grants():
    client = TestClient(app)
    headers = {"Authorization": "Bearer dev:owner@test.local"}
    org_id = _org_id()
    denied_grant = client.post(
        f"/v1/orgs/{org_id}/workspaces/ws-test/grants",
        params={"user_id": "someone-else"},
        headers=headers,
    )
    assert denied_grant.status_code == 403

    denied_revoke = client.delete(
        f"/v1/orgs/{org_id}/workspaces/ws-test/grants/someone-else",
        headers=headers,
    )
    assert denied_revoke.status_code == 403


def test_execution_cancel_api_cancels_queued_execution_and_audits(monkeypatch):
    monkeypatch.setattr(settings, "mock_runtime_enabled", True)
    org_id, workspace_id, task_id, agent_id = _seed_execution_records("mock")
    client = TestClient(app)
    headers = {"Authorization": "Bearer dev:owner@test.local"}
    created = client.post(
        f"/v1/orgs/{org_id}/executions",
        headers=headers,
        json={
            "workspace_id": workspace_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "idempotency_key": f"cancel-api-{uuid.uuid4().hex}",
        },
    )
    assert created.status_code == 201
    execution_id = created.json()["id"]

    cancelled = client.post(
        f"/v1/orgs/{org_id}/executions/{execution_id}/cancel",
        params={"workspace_id": workspace_id},
        headers=headers,
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    db = SessionLocal()
    try:
        saved = db.get(Execution, execution_id)
        assert saved.status == ExecutionStatus.cancelled
        assert saved.finished_at is not None
        assert db.query(AuditEvent).filter_by(
            resource_id=execution_id, event_type="execution.cancelled"
        ).count() == 1
    finally:
        db.close()


def test_execution_cancel_api_hides_cross_workspace_execution(monkeypatch):
    monkeypatch.setattr(settings, "mock_runtime_enabled", True)
    org_id, workspace_id, task_id, agent_id = _seed_execution_records("mock")
    client = TestClient(app)
    headers = {"Authorization": "Bearer dev:owner@test.local"}
    created = client.post(
        f"/v1/orgs/{org_id}/executions",
        headers=headers,
        json={
            "workspace_id": workspace_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "idempotency_key": f"cancel-scope-{uuid.uuid4().hex}",
        },
    )
    assert created.status_code == 201
    execution_id = created.json()["id"]

    denied = client.post(
        f"/v1/orgs/{org_id}/executions/{execution_id}/cancel",
        params={"workspace_id": "another-workspace"},
        headers=headers,
    )
    assert denied.status_code == 404


def test_execution_cancel_api_persists_request_for_active_execution(monkeypatch):
    monkeypatch.setattr(settings, "mock_runtime_enabled", True)
    org_id, workspace_id, task_id, agent_id = _seed_execution_records("mock")
    client = TestClient(app)
    headers = {"Authorization": "Bearer dev:owner@test.local"}
    created = client.post(
        f"/v1/orgs/{org_id}/executions",
        headers=headers,
        json={
            "workspace_id": workspace_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "idempotency_key": f"cancel-active-{uuid.uuid4().hex}",
        },
    )
    assert created.status_code == 201
    execution_id = created.json()["id"]

    db = SessionLocal()
    try:
        execution = db.get(Execution, execution_id)
        execution.status = ExecutionStatus.running
        db.commit()
    finally:
        db.close()

    response = client.post(
        f"/v1/orgs/{org_id}/executions/{execution_id}/cancel",
        params={"workspace_id": workspace_id},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert response.json()["control_request"]["action"] == "cancel"



def test_execution_pause_and_resume_api_for_unstarted_execution(monkeypatch):
    monkeypatch.setattr(settings, "mock_runtime_enabled", True)
    org_id, workspace_id, task_id, agent_id = _seed_execution_records("mock")
    client = TestClient(app)
    headers = {"Authorization": "Bearer dev:owner@test.local"}
    created = client.post(
        f"/v1/orgs/{org_id}/executions", headers=headers,
        json={"workspace_id": workspace_id, "task_id": task_id,
              "agent_id": agent_id, "idempotency_key": f"pause-api-{uuid.uuid4().hex}"},
    )
    assert created.status_code == 201
    execution_id = created.json()["id"]

    paused = client.post(
        f"/v1/orgs/{org_id}/executions/{execution_id}/pause",
        params={"workspace_id": workspace_id}, headers=headers,
    )
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"

    resumed = client.post(
        f"/v1/orgs/{org_id}/executions/{execution_id}/resume",
        params={"workspace_id": workspace_id}, headers=headers,
    )
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "queued"
    assert resumed.json()["control_request"]["action"] == "resume"



def test_outbox_summary_requires_authentication():
    client = TestClient(app)
    response = client.get(
        f"/v1/orgs/{_org_id()}/workspaces/ws-test/outbox/summary"
    )
    assert response.status_code == 401


def test_outbox_summary_rejects_organization_owner_without_founder_authority():
    client = TestClient(app)
    response = client.get(
        f"/v1/orgs/{_org_id()}/workspaces/ws-test/outbox/summary",
        headers={"Authorization": "Bearer dev:owner@test.local"},
    )
    assert response.status_code == 403


def test_outbox_summary_rejects_member_without_exact_workspace_grant():
    db = SessionLocal()
    try:
        viewer = User(
            email=f"outbox-viewer-{uuid.uuid4().hex}@test.local",
            display_name="Outbox Viewer",
        )
        db.add(viewer)
        db.flush()
        db.add(Membership(org_id=_org_id(), user_id=viewer.id, role=Role.viewer))
        db.commit()
        email = viewer.email
    finally:
        db.close()

    response = TestClient(app).get(
        f"/v1/orgs/{_org_id()}/workspaces/ws-test/outbox/summary",
        headers={"Authorization": f"Bearer dev:{email}"},
    )
    assert response.status_code == 404


def test_outbox_summary_founder_response_is_scoped_and_payload_free():
    org_id = _org_id()
    db = SessionLocal()
    try:
        owner = db.query(User).filter_by(email="owner@test.local").one()
        db.add(FounderAuthority(org_id=org_id, user_id=owner.id, active=True))
        db.add_all([
            OutboxEvent(
                org_id=org_id, workspace_id="ws-test", event_type="test.pending",
                schema_version=1, aggregate_type="test", aggregate_id=str(uuid.uuid4()),
                idempotency_key=f"outbox-api-pending-{uuid.uuid4().hex}",
                payload={"secret": "must-not-leak"}, status="pending",
            ),
            OutboxEvent(
                org_id=org_id, workspace_id="ws-test", event_type="test.published",
                schema_version=1, aggregate_type="test", aggregate_id=str(uuid.uuid4()),
                idempotency_key=f"outbox-api-published-{uuid.uuid4().hex}",
                payload={"published": True}, status="published",
            ),
        ])
        other_workspace = Workspace(
            id=f"outbox-other-{uuid.uuid4().hex[:12]}",
            org_id=org_id, name="Other Outbox Workspace",
        )
        db.add(other_workspace)
        db.flush()
        db.add(OutboxEvent(
            org_id=org_id, workspace_id=other_workspace.id, event_type="test.other",
            schema_version=1, aggregate_type="test", aggregate_id=str(uuid.uuid4()),
            idempotency_key=f"outbox-api-other-{uuid.uuid4().hex}",
            payload={"other_workspace": True}, status="pending",
        ))
        db.commit()
    finally:
        db.close()

    response = TestClient(app).get(
        f"/v1/orgs/{org_id}/workspaces/ws-test/outbox/summary",
        headers={"Authorization": "Bearer dev:owner@test.local"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["counts"] == {
        "pending": 1, "processing": 0, "published": 1, "dead_letter": 0,
    }
    assert body["total"] == 2
    assert "payload" not in body
    assert "secret" not in str(body)
    assert "other_workspace" not in str(body)


def test_execution_history_exposes_normalized_usage_without_transcript():
    org_id, workspace_id, task_id, agent_id = _seed_execution_records("mock")
    client = TestClient(app)
    headers = {"Authorization": "Bearer dev:owner@test.local"}
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(email="owner@test.local").one()
        execution = Execution(
            org_id=org_id, workspace_id=workspace_id, task_id=task_id, agent_id=agent_id,
            requested_by=user.id, idempotency_key=f"usage-api-{uuid.uuid4().hex}",
            runtime="mock", data_class=DataClass.synthetic, status=ExecutionStatus.succeeded,
        )
        db.add(execution); db.flush(); execution_id = execution.id
        execution.result = {
            "provider": "claude_managed_agents", "external_run_id": "sesn_usage",
            "status": "succeeded", "detail": "private transcript must not be exposed",
            "usage": {"input_tokens": 120, "output_tokens": 45,
                      "list_cost_minor": 7, "currency": "USD"},
        }
        db.commit()
    finally:
        db.close()
    listed = client.get(f"/v1/orgs/{org_id}/executions", params={"workspace_id": workspace_id}, headers=headers)
    assert listed.status_code == 200
    item = next(row for row in listed.json() if row["id"] == execution_id)
    assert item["provider_usage"] == {"input_tokens": 120, "output_tokens": 45,
                                      "list_cost_minor": 7, "currency": "USD"}
    assert "result" not in item and "detail" not in item
