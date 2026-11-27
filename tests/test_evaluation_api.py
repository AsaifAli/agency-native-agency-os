import os
os.environ["DATABASE_URL"] = "sqlite:///./test_agency_os.db"
os.environ["DEV_AUTH_ENABLED"] = "true"

from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, engine, SessionLocal
from app.models import User, Organization, Membership, Workspace, Role, WorkspaceGrant


def setup_module():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    user = User(email="eval-owner@test.local", display_name="Evaluation Owner")
    org = Organization(name="Evaluation Test Org")
    db.add_all([user, org])
    db.flush()
    db.add(Membership(org_id=org.id, user_id=user.id, role=Role.owner))
    workspace = Workspace(id="ws-eval-test", org_id=org.id, name="Evaluation Workspace")
    db.add(workspace)
    db.flush()
    db.add(WorkspaceGrant(
        org_id=org.id, workspace_id=workspace.id,
        user_id=user.id, granted_by=user.id,
    ))
    db.commit()
    db.close()


def _org_id():
    db = SessionLocal()
    try:
        return db.query(Organization).filter_by(name="Evaluation Test Org").one().id
    finally:
        db.close()


def test_evaluation_api_persists_tenant_scoped_run_and_audit():
    client = TestClient(app)
    headers = {"Authorization": "Bearer dev:eval-owner@test.local"}
    org_id = _org_id()
    response = client.post(
        f"/v1/orgs/{org_id}/evaluations",
        headers=headers,
        json={
            "workspace_id": "ws-eval-test",
            "pack_name": "agent_workflow",
            "expected": {"required_steps": ["plan"]},
            "actual": {
                "status": "completed",
                "completed_steps": ["plan"],
                "tool_call_validity": 1,
                "policy_pass_rate": 1,
                "approval_compliant": True,
                "execution_reliability": 1,
                "fallback_rate": 0,
            },
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["passed"] is True
    assert body["pack_name"] == "agent_workflow"

    listed = client.get(
        f"/v1/orgs/{org_id}/evaluations?workspace_id=ws-eval-test",
        headers=headers,
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_user_submitted_evaluation_is_never_marked_as_release_verified():
    client = TestClient(app)
    headers = {"Authorization": "Bearer dev:eval-owner@test.local"}
    org_id = _org_id()
    response = client.post(
        f"/v1/orgs/{org_id}/evaluations",
        headers=headers,
        json={
            "workspace_id": "ws-eval-test",
            "pack_name": "safety_security",
            "expected": {"required_controls": ["tenant_isolation"]},
            "actual": {
                "control_results": {"tenant_isolation": True},
                "tenant_isolation_passed": True,
                "data_policy_passed": True,
            },
        },
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["passed"] is True
    assert result["evidence_trust"] == "self_reported"
    assert result["release_eligible"] is False

    listed = client.get(
        f"/v1/orgs/{org_id}/evaluations?workspace_id=ws-eval-test",
        headers=headers,
    )
    assert listed.status_code == 200
    assert listed.json()[0]["evidence_trust"] == "self_reported"
    assert listed.json()[0]["release_eligible"] is False
