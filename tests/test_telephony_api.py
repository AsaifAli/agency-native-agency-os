import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.auth import Principal, get_principal
from app.db import Base, get_db
from app.models import Membership, Organization, Role, User, Workspace
from app.domain_models import Lead
from app.telephony.models import CallSession, CallTranscript, OutboxEvent
from app.telephony.routes import router
import app.domain_models  # noqa: F401
import app.telephony.models  # noqa: F401


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    db = TestingSession()
    user = User(email="voice-owner@example.test", display_name="Owner")
    org = Organization(name="Voice Test Org")
    other_org = Organization(name="Other Org")
    db.add_all([user, org, other_org]); db.flush()
    ws = Workspace(id="voice-ws", org_id=org.id, name="Workspace")
    other_ws = Workspace(id="voice-other-ws", org_id=other_org.id, name="Other")
    db.add_all([ws, other_ws])
    db.add(Membership(org_id=org.id, user_id=user.id, role=Role.owner)); db.flush()
    lead = Lead(org_id=org.id, workspace_id=ws.id, company_name="Acme", created_by=user.id)
    foreign_lead = Lead(org_id=other_org.id, workspace_id=other_ws.id, company_name="Foreign", created_by=user.id)
    db.add_all([lead, foreign_lead]); db.commit()
    app = FastAPI(); app.include_router(router)
    def override_db():
        session = TestingSession()
        try: yield session
        finally: session.close()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_principal] = lambda: Principal(user=user)
    tc = TestClient(app); tc.org_id = org.id; tc.ws_id = ws.id
    tc.lead_id = lead.id; tc.foreign_lead_id = foreign_lead.id
    yield tc
    db.close(); Base.metadata.drop_all(engine); engine.dispose()


def headers(): return {"Authorization": "Bearer test"}


def test_outbound_call_transcript_and_transactional_events(client):
    r = client.post(f"/v1/orgs/{client.org_id}/telephony/calls", headers=headers(), json={
        "workspace_id": client.ws_id, "direction": "outbound", "phone_number": "+919999999999",
        "lead_id": client.lead_id, "purpose": "Discovery call"
    })
    assert r.status_code == 201, r.text
    call = r.json(); assert call["status"] == "planned"
    call_id = call["id"]
    r = client.patch(f"/v1/orgs/{client.org_id}/telephony/calls/{call_id}", headers=headers(), json={"status": "queued"})
    assert r.status_code == 200, r.text
    r = client.patch(f"/v1/orgs/{client.org_id}/telephony/calls/{call_id}", headers=headers(), json={"status": "ringing", "provider": "test-provider", "provider_call_id": "call-123"})
    assert r.status_code == 200, r.text
    r = client.patch(f"/v1/orgs/{client.org_id}/telephony/calls/{call_id}", headers=headers(), json={"status": "in_progress"})
    assert r.status_code == 200, r.text
    r = client.patch(f"/v1/orgs/{client.org_id}/telephony/calls/{call_id}", headers=headers(), json={
        "status": "completed", "outcome": "qualified", "summary": "Interested in workflow automation", "duration_seconds": 240
    })
    assert r.status_code == 200, r.text
    r = client.post(f"/v1/orgs/{client.org_id}/telephony/calls/{call_id}/transcripts", headers=headers(), json={
        "transcript_text": "Client: We need to automate reporting.", "language": "en", "source": "manual"
    })
    assert r.status_code == 201, r.text
    assert r.json()["call_id"] == call_id
    r = client.get(f"/v1/orgs/{client.org_id}/telephony/calls/{call_id}/transcripts", headers=headers())
    assert r.status_code == 200 and len(r.json()) == 1


def test_cross_workspace_lead_reference_rejected(client):
    r = client.post(f"/v1/orgs/{client.org_id}/telephony/calls", headers=headers(), json={
        "workspace_id": client.ws_id, "direction": "inbound", "phone_number": "+919999999999",
        "lead_id": client.foreign_lead_id
    })
    assert r.status_code == 404


def test_terminal_call_cannot_be_mutated(client):
    r = client.post(f"/v1/orgs/{client.org_id}/telephony/calls", headers=headers(), json={
        "workspace_id": client.ws_id, "direction": "inbound", "phone_number": "+919999999999"
    })
    call_id = r.json()["id"]
    r = client.patch(f"/v1/orgs/{client.org_id}/telephony/calls/{call_id}", headers=headers(), json={"status": "in_progress"})
    assert r.status_code == 200
    r = client.patch(f"/v1/orgs/{client.org_id}/telephony/calls/{call_id}", headers=headers(), json={"status": "completed"})
    assert r.status_code == 200
    r = client.patch(f"/v1/orgs/{client.org_id}/telephony/calls/{call_id}", headers=headers(), json={"status": "failed"})
    assert r.status_code == 409
