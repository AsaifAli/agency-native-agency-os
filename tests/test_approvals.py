
import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.db import Base, engine, SessionLocal
from app.models import (
    User,
    Organization,
    Membership,
    Workspace,
    Role,
    FounderAuthority,
    WorkspaceGrant,
)

client = TestClient(app)

# These routes require an explicit workspace query scope. Keep test calls concise
# while preserving any deliberately supplied (including cross-workspace) scope.
_original_client_request = client.request

def _workspace_scoped_request(method, url, **kwargs):
    url_text = str(url)
    params = kwargs.get("params")
    if "/v1/orgs/" in url_text and "workspace_id=" not in url_text:
        scoped_params = dict(params or {})
        scoped_params.setdefault("workspace_id", WORKSPACE_ID)
        kwargs["params"] = scoped_params
    return _original_client_request(method, url, **kwargs)

client.request = _workspace_scoped_request

OWNER_EMAIL = "approval-owner@test.local"
ADMIN_EMAIL = "approval-admin@test.local"
REVIEWER_EMAIL = "approval-reviewer@test.local"
FOUNDER_EMAIL = "approval-founder@test.local"
OPERATOR_EMAIL = "approval-operator@test.local"
ORG_NAME = "Approval Test Org"
WORKSPACE_ID = "approval-ws-test"


def setup_module():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        org = db.query(Organization).filter_by(name=ORG_NAME).first()
        if org is None:
            org = Organization(name=ORG_NAME)
            db.add(org)
            db.flush()

        users_and_roles = [
            (OWNER_EMAIL, "Owner", Role.owner),
            (ADMIN_EMAIL, "Admin", Role.admin),
            (REVIEWER_EMAIL, "Reviewer", Role.reviewer),
            (OPERATOR_EMAIL, "Operator", Role.operator),
            (FOUNDER_EMAIL, "Founder Authority", Role.viewer),
        ]

        for email, display_name, role in users_and_roles:
            user = db.query(User).filter_by(email=email).first()
            if user is None:
                user = User(email=email, display_name=display_name)
                db.add(user)
                db.flush()

            membership = db.query(Membership).filter_by(
                org_id=org.id,
                user_id=user.id,
            ).first()

            if membership is None:
                db.add(
                    Membership(
                        org_id=org.id,
                        user_id=user.id,
                        role=role,
                    )
                )

        founder_user = db.query(User).filter_by(email=FOUNDER_EMAIL).one()
        founder_grant = db.query(FounderAuthority).filter_by(
            org_id=org.id, user_id=founder_user.id
        ).first()
        if founder_grant is None:
            db.add(FounderAuthority(
                org_id=org.id, user_id=founder_user.id, grant_source="test_fixture"
            ))

        workspace = db.query(Workspace).filter_by(
            id=WORKSPACE_ID
        ).first()

        if workspace is None:
            db.add(
                Workspace(
                    id=WORKSPACE_ID,
                    org_id=org.id,
                    name="Approval Workspace",
                )
            )
            db.flush()

        workspace = db.query(Workspace).filter_by(id=WORKSPACE_ID).one()
        grantor = db.query(User).filter_by(email=OWNER_EMAIL).one()
        for email, _, _ in users_and_roles:
            user = db.query(User).filter_by(email=email).one()
            grant = db.query(WorkspaceGrant).filter_by(
                org_id=org.id, workspace_id=workspace.id, user_id=user.id,
            ).filter(WorkspaceGrant.revoked_at.is_(None)).first()
            if grant is None:
                db.add(WorkspaceGrant(
                    org_id=org.id, workspace_id=workspace.id,
                    user_id=user.id, granted_by=grantor.id,
                ))

        db.commit()
    finally:
        db.close()


def _org_id():
    db = SessionLocal()
    try:
        return db.query(Organization).filter_by(name=ORG_NAME).one().id
    finally:
        db.close()


def _headers(email):
    return {"Authorization": f"Bearer dev:{email}"}


def _create_request():
    org_id = _org_id()
    payload = {
        "workspace_id": WORKSPACE_ID,
        "action_type": "production.release",
        "resource_id": str(uuid.uuid4()),
        "idempotency_key": f"approval-test-{uuid.uuid4().hex}",
        "request_payload": {"reason": "release review"},
    }

    response = client.post(
        f"/v1/orgs/{org_id}/approvals",
        json=payload,
        headers=_headers(OPERATOR_EMAIL),
    )
    assert response.status_code == 201, response.text

    return org_id, response.json()


def _decide(org_id, approval_id, email):
    return client.post(
        f"/v1/orgs/{org_id}/approvals/{approval_id}/decision",
        json={"decision": "approved", "note": "approval test"},
        headers=_headers(email),
    )


def test_approval_request_is_idempotent_and_explicit_founder_can_approve():
    org_id = _org_id()
    payload = {
        "workspace_id": WORKSPACE_ID,
        "action_type": "production.release",
        "resource_id": "release-idempotency-test",
        "idempotency_key": f"approval-idempotency-{uuid.uuid4().hex}",
        "request_payload": {"reason": "release review"},
    }

    operator_headers = _headers(OPERATOR_EMAIL)
    first = client.post(
        f"/v1/orgs/{org_id}/approvals", json=payload, headers=operator_headers
    )
    assert first.status_code == 201, first.text
    second = client.post(
        f"/v1/orgs/{org_id}/approvals", json=payload, headers=operator_headers
    )
    assert second.status_code == 201, second.text
    assert first.json()["id"] == second.json()["id"]
    approval_id = first.json()["id"]

    # Organization owner is not automatically founder authority.
    owner_decision = _decide(org_id, approval_id, OWNER_EMAIL)
    assert owner_decision.status_code == 403

    # Explicit founder authority is independent of the user's organization role.
    founder_decision = _decide(org_id, approval_id, FOUNDER_EMAIL)
    assert founder_decision.status_code == 200, founder_decision.text
    assert founder_decision.json()["status"] == "approved"


def test_explicit_founder_viewer_can_list_approval_queue():
    org_id, approval = _create_request()
    response = client.get(
        f"/v1/orgs/{org_id}/approvals",
        headers=_headers(FOUNDER_EMAIL),
    )
    assert response.status_code == 200, response.text
    assert any(item["id"] == approval["id"] for item in response.json())


def test_founder_can_request_and_approve_own_decision():
    org_id = _org_id()
    payload = {
        "workspace_id": WORKSPACE_ID,
        "action_type": "pricing.change",
        "resource_id": "founder-initiated-pricing-review",
        "idempotency_key": f"founder-own-{uuid.uuid4().hex}",
        "request_payload": {"reason": "Founder initiated protected change"},
    }
    requested = client.post(
        f"/v1/orgs/{org_id}/approvals",
        json=payload,
        headers=_headers(FOUNDER_EMAIL),
    )
    assert requested.status_code == 201, requested.text
    decided = _decide(org_id, requested.json()["id"], FOUNDER_EMAIL)
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "approved"


def test_admin_cannot_decide_approval():
    org_id, approval = _create_request()

    response = _decide(org_id, approval["id"], ADMIN_EMAIL)

    assert response.status_code == 403


def test_reviewer_cannot_decide_approval():
    org_id, approval = _create_request()

    response = _decide(org_id, approval["id"], REVIEWER_EMAIL)

    assert response.status_code == 403
