import os
import uuid
os.environ["DATABASE_URL"] = "sqlite:///./test_agency_os.db"
os.environ["DEV_AUTH_ENABLED"] = "true"
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, engine, SessionLocal
from app.models import (
    User, Organization, Membership, Workspace, Role,
    Agent, Task, DataClass, AuditEvent, Execution, ExecutionStatus,
)
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
    db.add(Workspace(id="ws-test", org_id=org.id, name="Test Workspace"))
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
        assert saved.status == ExecutionStatus.succeeded
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
