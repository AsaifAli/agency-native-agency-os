from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models import User, Organization, Membership, Workspace, Role

client = TestClient(app)

def setup_module():
    db = SessionLocal()
    try:
        owner = db.query(User).filter_by(email="approval-owner@test.local").first()
        if not owner:
            owner = User(email="approval-owner@test.local", display_name="Requester")
            reviewer = User(email="approval-reviewer@test.local", display_name="Reviewer")
            org = Organization(name="Approval Test Org")
            db.add_all([owner, reviewer, org]); db.flush()
            db.add_all([
                Membership(org_id=org.id, user_id=owner.id, role=Role.owner),
                Membership(org_id=org.id, user_id=reviewer.id, role=Role.reviewer),
                Workspace(id="approval-ws-test", org_id=org.id, name="Approval Workspace")
            ])
            db.commit()
    finally:
        db.close()

def _org_id():
    db = SessionLocal()
    try:
        return db.query(Organization).filter_by(name="Approval Test Org").one().id
    finally:
        db.close()

def test_approval_request_is_idempotent_and_requester_cannot_approve():
    org_id = _org_id()
    payload = {
        "workspace_id": "approval-ws-test",
        "action_type": "production.release",
        "resource_id": "release-123",
        "idempotency_key": "approval-test-key-0001",
        "request_payload": {"reason": "release review"}
    }
    owner_headers = {"Authorization": "Bearer dev:approval-owner@test.local"}
    first = client.post(f"/v1/orgs/{org_id}/approvals", json=payload, headers=owner_headers)
    assert first.status_code == 201, first.text
    second = client.post(f"/v1/orgs/{org_id}/approvals", json=payload, headers=owner_headers)
    assert second.status_code == 201, second.text
    assert first.json()["id"] == second.json()["id"]
    own_decision = client.post(
        f"/v1/orgs/{org_id}/approvals/{first.json()['id']}/decision",
        json={"decision": "approved", "note": "self approve"},
        headers=owner_headers
    )
    assert own_decision.status_code == 403

    reviewer_headers = {"Authorization": "Bearer dev:approval-reviewer@test.local"}
    decision = client.post(
        f"/v1/orgs/{org_id}/approvals/{first.json()['id']}/decision",
        json={"decision": "approved", "note": "reviewed"},
        headers=reviewer_headers
    )
    assert decision.status_code == 200, decision.text
    assert decision.json()["status"] == "approved"
