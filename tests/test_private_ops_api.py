from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import Principal, get_principal
from app.db import Base, get_db, set_rls_context
from app.models import FounderAuthority, Membership, Organization, Role, User, Workspace, WorkspaceGrant
from app.domain_models import Lead, Opportunity
from app.private_ops_routes import router


@pytest.fixture()
def private_ops_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    db = factory()
    user = User(email="private-ops@example.test", display_name="Founder")
    org = Organization(name="Private Ops")
    other_org = Organization(name="Other")
    db.add_all([user, org, other_org]); db.flush()
    ws = Workspace(id="private-ws", org_id=org.id, name="Private")
    other_ws = Workspace(id="other-ws", org_id=other_org.id, name="Other")
    db.add_all([ws, other_ws, Membership(org_id=org.id, user_id=user.id, role=Role.owner),
                FounderAuthority(org_id=org.id, user_id=user.id, grant_source="test"),
                WorkspaceGrant(org_id=org.id, workspace_id=ws.id, user_id=user.id, granted_by=user.id)])
    lead = Lead(org_id=org.id, workspace_id=ws.id, company_name="Northwind", contact_name="Buyer",
                email="buyer@example.test", source="website", created_by=user.id)
    opportunity = Opportunity(org_id=org.id, workspace_id=ws.id, title="AI discovery",
        amount_minor=250000, currency="INR", probability=50, owner_user_id=user.id)
    db.add_all([lead, opportunity]); db.commit()
    app = FastAPI(); app.include_router(router)
    principal = {"user": user}
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
    client.org_id, client.ws_id, client.other_ws_id, client.lead_id, client.opportunity_id, client.user_id = org.id, ws.id, other_ws.id, lead.id, opportunity.id, user.id
    client.session_factory = factory
    client.set_principal = lambda selected_user: principal.update(user=selected_user)
    yield client
    db.close(); Base.metadata.drop_all(engine); engine.dispose()


def test_knowledge_item_is_versioned_and_workspace_scoped(private_ops_client):
    c = private_ops_client
    response = c.post(f"/v1/orgs/{c.org_id}/knowledge", json={
        "workspace_id": c.ws_id, "key": "delivery.playbook", "title": "Delivery playbook",
        "content": "Use a staged rollout.", "source_type": "founder_note", "source_reference": "founder:2026-11",
        "classification": "internal",
    })
    assert response.status_code == 201, response.text
    first = response.json()
    assert first["version"] == 1 and first["status"] == "draft"
    second = c.post(f"/v1/orgs/{c.org_id}/knowledge", json={
        "workspace_id": c.ws_id, "key": "delivery.playbook", "title": "Delivery playbook",
        "content": "Use a staged rollout with a rollback plan.", "source_type": "founder_note",
        "source_reference": "founder:2026-11", "classification": "internal",
    })
    assert second.status_code == 201 and second.json()["version"] == 2
    listed = c.get(f"/v1/orgs/{c.org_id}/knowledge", params={"workspace_id": c.ws_id})
    assert listed.status_code == 200 and len(listed.json()) == 2
    hidden = c.get(f"/v1/orgs/{c.org_id}/knowledge", params={"workspace_id": c.other_ws_id})
    assert hidden.status_code in {403, 404}


def test_knowledge_blocks_secrets_and_requires_founder_to_approve(private_ops_client):
    c = private_ops_client
    response = c.post(f"/v1/orgs/{c.org_id}/knowledge", json={
        "workspace_id": c.ws_id, "key": "secrets.bad", "title": "Unsafe", "content": "api_key=sk-ant-abcdefghijklmnop",
        "source_type": "founder_note", "source_reference": "manual", "classification": "confidential",
    })
    assert response.status_code == 422
    created = c.post(f"/v1/orgs/{c.org_id}/knowledge", json={
        "workspace_id": c.ws_id, "key": "policy", "title": "Policy", "content": "Internal policy.",
        "source_type": "founder_note", "source_reference": "manual", "classification": "internal",
    })
    item_id = created.json()["id"]
    approved = c.post(f"/v1/orgs/{c.org_id}/knowledge/{item_id}/approve", json={"workspace_id": c.ws_id})
    assert approved.status_code == 200 and approved.json()["status"] == "approved"
    approved_only = c.get(f"/v1/orgs/{c.org_id}/knowledge", params={"workspace_id": c.ws_id, "approved_only": "true"})
    assert approved_only.status_code == 200 and len(approved_only.json()) == 1


def test_business_workflow_drafts_require_real_workspace_sources(private_ops_client):
    c = private_ops_client
    created = c.post(f"/v1/orgs/{c.org_id}/business-drafts", json={
        "workspace_id": c.ws_id, "kind": "front_desk",
        "source_refs": [{"type": "lead", "id": c.lead_id}],
        "content": {"summary": "Qualified enquiry", "suggested_reply": "Thank you for reaching out."},
    })
    assert created.status_code == 201, created.text
    item = created.json()
    assert item["status"] == "draft" and item["source_refs"][0]["id"] == c.lead_id
    reviewed = c.post(f"/v1/orgs/{c.org_id}/business-drafts/{item['id']}/review",
        json={"workspace_id": c.ws_id, "decision": "reviewed"})
    assert reviewed.status_code == 200 and reviewed.json()["status"] == "reviewed"
    wrong_scope = c.post(f"/v1/orgs/{c.org_id}/business-drafts", json={
        "workspace_id": c.ws_id, "kind": "front_desk",
        "source_refs": [{"type": "lead", "id": "not-a-lead-in-this-workspace"}],
        "content": {"summary": "Should not persist"},
    })
    assert wrong_scope.status_code == 404


def test_meeting_to_proposal_requires_opportunity_and_founder_brief_is_read_only(private_ops_client):
    c = private_ops_client
    draft = c.post(f"/v1/orgs/{c.org_id}/business-drafts", json={
        "workspace_id": c.ws_id, "kind": "meeting_proposal",
        "source_refs": [{"type": "opportunity", "id": c.opportunity_id}],
        "content": {"scope": "Draft only"},
    })
    assert draft.status_code == 201 and draft.json()["status"] == "draft"
    brief = c.get(f"/v1/orgs/{c.org_id}/founder-brief", params={"workspace_id": c.ws_id})
    assert brief.status_code == 200
    assert brief.json()["signals"]["new_leads"] == 1
    assert "note" in brief.json()
    assert brief.json()["signals"]["open_opportunities"] == 1


def test_draft_payload_is_redacted_and_workspace_member_role_cannot_approve_knowledge(private_ops_client):
    c = private_ops_client
    created = c.post(f"/v1/orgs/{c.org_id}/business-drafts", json={
        "workspace_id": c.ws_id, "kind": "front_desk",
        "source_refs": [{"type": "lead", "id": c.lead_id}],
        "content": {"summary": "Contact buyer@example.com for next steps"},
    })
    assert created.status_code == 201
    assert "buyer@example.com" not in created.json()["content"]["summary"]
    assert "[REDACTED_EMAIL]" in created.json()["content"]["summary"]

    db = c.session_factory()
    try:
        other = User(email="owner-without-founder@example.test", display_name="Org Owner")
        db.add(other); db.flush()
        db.add_all([
            Membership(org_id=c.org_id, user_id=other.id, role=Role.owner),
            WorkspaceGrant(org_id=c.org_id, workspace_id=c.ws_id, user_id=other.id, granted_by=c.user_id),
        ])
        db.commit()
    finally:
        db.close()
    c.set_principal(other)
    knowledge = c.post(f"/v1/orgs/{c.org_id}/knowledge", json={
        "workspace_id": c.ws_id, "key": "review.policy", "title": "Review policy",
        "content": "Owner role is not founder authority.", "source_type": "policy",
        "source_reference": "policy:test", "classification": "internal",
    })
    assert knowledge.status_code == 201
    denied = c.post(f"/v1/orgs/{c.org_id}/knowledge/{knowledge.json()['id']}/approve",
        json={"workspace_id": c.ws_id})
    assert denied.status_code == 403
