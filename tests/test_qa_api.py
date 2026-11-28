import pytest
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import Principal, get_principal
from app.db import Base, get_db, set_rls_context
from app.domain_models import Project
from app.models import (
    EvaluationRun, Membership, Organization, Role, Task, User, Workspace,
    WorkspaceGrant,
)
from app.qa_routes import router


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    db = TestingSession()
    user = User(email="qa-owner@example.test", display_name="QA Owner")
    org = Organization(name="QA Test Org")
    other_org = Organization(name="QA Other Org")
    db.add_all([user, org, other_org])
    db.flush()
    ws = Workspace(id="qa-ws", org_id=org.id, name="QA Workspace")
    other_ws = Workspace(id="qa-other-ws", org_id=other_org.id, name="Other Workspace")
    db.add_all([ws, other_ws])
    db.add(Membership(org_id=org.id, user_id=user.id, role=Role.owner))
    db.flush()
    db.add(WorkspaceGrant(
        org_id=org.id, workspace_id=ws.id, user_id=user.id, granted_by=user.id,
    ))
    project = Project(
        org_id=org.id, workspace_id=ws.id, name="QA Project",
        owner_user_id=user.id,
    )
    foreign_project = Project(
        org_id=other_org.id, workspace_id=other_ws.id, name="Foreign Project",
        owner_user_id=user.id,
    )
    db.add_all([project, foreign_project])
    db.flush()
    task = Task(
        org_id=org.id, workspace_id=ws.id, title="Implement workflow",
        description="", created_by=user.id,
    )
    foreign_task = Task(
        org_id=other_org.id, workspace_id=other_ws.id, title="Foreign task",
        description="", created_by=user.id,
    )
    db.add_all([task, foreign_task])
    db.flush()
    passing = EvaluationRun(
        org_id=org.id, workspace_id=ws.id, task_id=task.id,
        pack_name="agent_workflow", score=1.0, passed=True,
        metrics={}, gate_results={}, evidence_trust="self_reported",
        created_by=user.id,
    )
    failing = EvaluationRun(
        org_id=org.id, workspace_id=ws.id, task_id=task.id,
        pack_name="agent_workflow", score=0.2, passed=False,
        metrics={}, gate_results={}, evidence_trust="self_reported",
        created_by=user.id,
    )
    wrong_task_eval = EvaluationRun(
        org_id=org.id, workspace_id=ws.id, task_id=None,
        pack_name="agent_workflow", score=1.0, passed=True,
        metrics={}, gate_results={}, evidence_trust="self_reported",
        created_by=user.id,
    )
    db.add_all([passing, failing, wrong_task_eval])
    db.commit()

    app = FastAPI()
    app.include_router(router)
    principal = {"user": user}

    def override_db():
        session = TestingSession()
        try:
            set_rls_context(session, user_id=principal["user"].id)
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_principal] = lambda: Principal(user=principal["user"])
    tc = TestClient(app)
    tc.org_id, tc.ws_id = org.id, ws.id
    tc.project_id, tc.task_id = project.id, task.id
    tc.foreign_project_id, tc.foreign_task_id = foreign_project.id, foreign_task.id
    tc.passing_eval_id, tc.failing_eval_id = passing.id, failing.id
    tc.wrong_task_eval_id = wrong_task_eval.id
    tc.session_factory = TestingSession
    yield tc
    db.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def headers():
    return {"Authorization": "Bearer qa-test"}


def create_issue(client):
    return client.post(
        f"/v1/orgs/{client.org_id}/qa/issues",
        headers=headers(),
        json={
            "workspace_id": client.ws_id,
            "project_id": client.project_id,
            "task_id": client.task_id,
            "title": "Workflow skips approval validation",
            "description": "A generated execution proceeds without the required approval.",
            "severity": "critical",
            "reproducible_steps": ["Create a workflow", "Omit approval", "Run workflow"],
            "expected_result": "Execution is blocked pending approval.",
            "actual_result": "Execution starts without approval.",
            "evidence_references": ["artifact:synthetic-run-01"],
        },
    )


def test_qa_issue_creation_is_workspace_scoped_and_audited(client):
    response = create_issue(client)
    assert response.status_code == 201, response.text
    issue = response.json()
    assert issue["status"] == "open"
    assert issue["severity"] == "critical"
    assert issue["task_id"] == client.task_id

    db = client.session_factory()
    try:
        from app.models import AuditEvent
        event = db.query(AuditEvent).filter_by(
            resource_type="qa_issue", resource_id=issue["id"],
            event_type="qa_issue.created",
        ).one()
        assert event.workspace_id == client.ws_id
    finally:
        db.close()


def test_qa_issue_rejects_project_or_task_from_another_workspace(client):
    response = client.post(
        f"/v1/orgs/{client.org_id}/qa/issues",
        headers=headers(),
        json={
            "workspace_id": client.ws_id,
            "project_id": client.project_id,
            "task_id": client.foreign_task_id,
            "title": "Cross-workspace issue",
            "description": "Must not link a task from another workspace.",
            "severity": "major",
        },
    )
    assert response.status_code == 404


def test_qa_issue_requires_a_passing_task_linked_retest_before_closure(client):
    created = create_issue(client)
    assert created.status_code == 201, created.text
    issue_id = created.json()["id"]
    url = f"/v1/orgs/{client.org_id}/qa/issues/{issue_id}/transition?workspace_id={client.ws_id}"

    for status in ("triaged", "in_progress", "fixed", "retest"):
        response = client.patch(url, headers=headers(), json={"status": status})
        assert response.status_code == 200, response.text

    missing_evidence = client.patch(
        url, headers=headers(), json={"status": "closed"},
    )
    assert missing_evidence.status_code == 422

    failed_evidence = client.patch(
        url, headers=headers(),
        json={"status": "closed", "retest_evaluation_run_id": client.failing_eval_id},
    )
    assert failed_evidence.status_code == 409

    wrong_task_evidence = client.patch(
        url, headers=headers(),
        json={"status": "closed", "retest_evaluation_run_id": client.wrong_task_eval_id},
    )
    assert wrong_task_evidence.status_code == 409

    # Retest evidence must be generated after the issue was marked fixed.
    db = client.session_factory()
    try:
        evaluation = db.get(EvaluationRun, client.passing_eval_id)
        evaluation.created_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()

    closed = client.patch(
        url, headers=headers(),
        json={"status": "closed", "retest_evaluation_run_id": client.passing_eval_id},
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "closed"
    assert closed.json()["retest_evaluation_run_id"] == client.passing_eval_id
    assert closed.json()["retest_evidence_trust"] == "self_reported"


def test_qa_issue_rejects_skipped_lifecycle_transitions(client):
    created = create_issue(client)
    assert created.status_code == 201, created.text
    response = client.patch(
        f"/v1/orgs/{client.org_id}/qa/issues/{created.json()['id']}/transition?workspace_id={client.ws_id}",
        headers=headers(), json={"status": "closed", "retest_evaluation_run_id": client.passing_eval_id},
    )
    assert response.status_code == 409


def test_qa_issue_list_is_limited_to_the_requested_workspace(client):
    created = create_issue(client)
    assert created.status_code == 201, created.text
    listed = client.get(
        f"/v1/orgs/{client.org_id}/qa/issues",
        headers=headers(), params={"workspace_id": client.ws_id},
    )
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()] == [created.json()["id"]]


def test_failed_retest_returns_issue_to_work_and_is_audited(client):
    created = create_issue(client)
    assert created.status_code == 201, created.text
    issue_id = created.json()["id"]
    url = f"/v1/orgs/{client.org_id}/qa/issues/{issue_id}/transition?workspace_id={client.ws_id}"
    for status in ("triaged", "in_progress", "fixed", "retest"):
        response = client.patch(url, headers=headers(), json={"status": status})
        assert response.status_code == 200, response.text

    db = client.session_factory()
    try:
        evaluation = db.get(EvaluationRun, client.failing_eval_id)
        evaluation.created_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()

    reopened = client.patch(
        url, headers=headers(),
        json={
            "status": "in_progress",
            "retest_evaluation_run_id": client.failing_eval_id,
            "note": "Retest still reproduces the issue; return it to implementation.",
        },
    )
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["status"] == "in_progress"
    assert reopened.json()["fixed_at"] is None

    db = client.session_factory()
    try:
        from app.models import AuditEvent
        event = db.query(AuditEvent).filter_by(
            resource_type="qa_issue", resource_id=issue_id,
            event_type="qa_issue.status_changed",
        ).order_by(AuditEvent.created_at.desc()).first()
        assert event.payload["retest_evaluation_run_id"] == client.failing_eval_id
        assert event.payload["from_status"] == "retest"
        assert event.payload["to_status"] == "in_progress"
    finally:
        db.close()


def test_qa_issue_redacts_pii_before_persistence(client):
    payload = {
        "workspace_id": client.ws_id,
        "project_id": client.project_id,
        "task_id": client.task_id,
        "title": "Contact alice@example.test reported approval bypass",
        "description": "Reproduced by alice@example.test in the test workspace.",
        "severity": "major",
    }
    response = client.post(
        f"/v1/orgs/{client.org_id}/qa/issues",
        headers=headers(), json=payload,
    )
    assert response.status_code == 201, response.text
    assert "alice@example.test" not in response.json()["title"]
    assert "alice@example.test" not in response.json()["description"]
    assert "[REDACTED_EMAIL]" in response.json()["description"]


def test_qa_issue_blocks_provider_secrets(client):
    response = client.post(
        f"/v1/orgs/{client.org_id}/qa/issues",
        headers=headers(),
        json={
            "workspace_id": client.ws_id,
            "project_id": client.project_id,
            "task_id": client.task_id,
            "title": "Provider key leaked in logs",
            "description": "Observed key sk-or-v1-abcdefghijklmnopqrstuvwx in output.",
            "severity": "critical",
        },
    )
    assert response.status_code == 422
    assert "data-protection" in response.json()["detail"].lower()
