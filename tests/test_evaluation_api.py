import os
import uuid
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


def test_outcome_measurement_links_workspace_scoped_evaluation_run():
    client = TestClient(app)
    headers = {"Authorization": "Bearer dev:eval-owner@test.local"}
    org_id = _org_id()
    suffix = uuid.uuid4().hex[:8]
    workspace_id = "ws-eval-test"

    project = client.post(
        f"/v1/orgs/{org_id}/projects", headers=headers,
        json={"workspace_id": workspace_id, "name": f"Evaluation evidence {suffix}"},
    )
    assert project.status_code == 201, project.text
    outcome = client.post(
        f"/v1/orgs/{org_id}/projects/{project.json()['id']}/outcomes",
        headers=headers, json={
            "workspace_id": workspace_id, "title": "Improve agent workflow reliability",
            "problem_statement": "Workflow completion is not consistently verified.",
            "desired_outcome": "Verify the workflow against an agreed evaluation pack.",
            "metric_name": "Workflow evaluation score", "metric_unit": "score",
            "direction": "increase", "target_value": "1",
            "measurement_method": "Run the agent workflow evaluation pack against synthetic evidence.",
            "acceptance_criteria": ["The agreed workflow evaluation is reviewed."],
        },
    )
    assert outcome.status_code == 201, outcome.text

    evaluation_payload = {
        "pack_name": "agent_workflow",
        "expected": {"required_steps": ["plan"]},
        "actual": {
            "status": "completed", "completed_steps": ["plan"],
            "tool_call_validity": 1, "policy_pass_rate": 1,
            "approval_compliant": True, "execution_reliability": 1,
            "fallback_rate": 0,
        },
    }
    evaluation = client.post(
        f"/v1/orgs/{org_id}/evaluations", headers=headers,
        json={"workspace_id": workspace_id, **evaluation_payload},
    )
    assert evaluation.status_code == 201, evaluation.text
    assert evaluation.json()["evidence_trust"] == "self_reported"
    assert evaluation.json()["release_eligible"] is False

    measurement_payload = {
        "workspace_id": workspace_id, "value": "1", "source_type": "agency_measured",
        "source_reference": "Evaluation run " + evaluation.json()["id"],
        "evidence_summary": "Evaluation result attached for review; not independent release verification.",
        "supporting_evaluation_run_id": evaluation.json()["id"],
    }
    measurement = client.post(
        f"/v1/orgs/{org_id}/outcomes/{outcome.json()['id']}/measurements",
        headers=headers, json=measurement_payload,
    )
    assert measurement.status_code == 201, measurement.text
    assert measurement.json()["supporting_evaluation_run_id"] == evaluation.json()["id"]

    other_workspace = client.post(
        f"/v1/orgs/{org_id}/workspaces", headers=headers,
        json={"name": f"Foreign evaluation workspace {suffix}"},
    )
    assert other_workspace.status_code == 201, other_workspace.text
    foreign_evaluation = client.post(
        f"/v1/orgs/{org_id}/evaluations", headers=headers,
        json={"workspace_id": other_workspace.json()["id"], **evaluation_payload},
    )
    assert foreign_evaluation.status_code == 201, foreign_evaluation.text

    cross_workspace = client.post(
        f"/v1/orgs/{org_id}/outcomes/{outcome.json()['id']}/measurements",
        headers=headers, json={
            **measurement_payload,
            "source_reference": "Foreign evaluation run " + foreign_evaluation.json()["id"],
            "supporting_evaluation_run_id": foreign_evaluation.json()["id"],
        },
    )
    assert cross_workspace.status_code == 404

