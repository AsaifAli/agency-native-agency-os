import pytest
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import Principal, get_principal
from app.db import Base, get_db
from app.models import Approval, ApprovalStatus, FounderAuthority, Membership, Organization, Role, User, Workspace
from app.domain_models import Contact, Lead
import app.domain_models  # noqa: F401
import app.operations_models  # noqa: F401
import app.telephony.models  # noqa: F401
import app.workforce_models  # noqa: F401
from app.outreach.models import OutboundMessage, CommunicationBlock, CommunicationConsent
import app.outreach.models  # noqa: F401
from app.outreach.routes import router


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    db = TestingSession()
    founder = User(email="outreach-founder@example.test", display_name="Founder")
    org = Organization(name="Outreach Test Org")
    other_org = Organization(name="Other Outreach Org")
    db.add_all([founder, org, other_org])
    db.flush()
    ws = Workspace(id="outreach-ws", org_id=org.id, name="Workspace")
    other_ws = Workspace(id="other-outreach-ws", org_id=other_org.id, name="Other")
    db.add_all([ws, other_ws])
    db.add(Membership(org_id=org.id, user_id=founder.id, role=Role.owner))
    db.add(FounderAuthority(org_id=org.id, user_id=founder.id, grant_source="test"))
    db.flush()
    contact = Contact(
        org_id=org.id, workspace_id=ws.id, first_name="Asha",
        email="asha@example.test", created_by=founder.id,
    )
    foreign_contact = Contact(
        org_id=other_org.id, workspace_id=other_ws.id, first_name="Foreign",
        email="foreign@example.test", created_by=founder.id,
    )
    db.add_all([contact, foreign_contact])
    db.flush()
    lead = Lead(
        org_id=org.id, workspace_id=ws.id, contact_id=contact.id,
        company_name="Acme", email=contact.email, source="referral",
        stage="qualified", score=80, created_by=founder.id,
    )
    db.add(lead)
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
    app.dependency_overrides[get_principal] = lambda: Principal(user=founder)
    test_client = TestClient(app)
    test_client.org_id = org.id
    test_client.ws_id = ws.id
    test_client.other_ws_id = other_ws.id
    test_client.user_id = founder.id
    test_client.contact_id = contact.id
    test_client.foreign_contact_id = foreign_contact.id
    test_client.lead_id = lead.id
    test_client.session_factory = TestingSession
    test_client.founder = founder
    yield test_client
    db.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def auth():
    return {"Authorization": "Bearer test"}


def _create_sender(client, email="hello@example.test", max_per_hour=10):
    response = client.post(
        "/v1/orgs/" + client.org_id + "/outreach/senders",
        headers=auth(), json={
            "workspace_id": client.ws_id, "display_name": "Agency Team",
            "email_address": email, "max_per_hour": max_per_hour, "max_per_day": 50,
        },
    )
    assert response.status_code == 201, response.text
    sender_id = response.json()["id"]
    active = client.patch(
        "/v1/orgs/" + client.org_id + "/outreach/senders/" + sender_id + "/status",
        headers=auth(), json={"status": "active"},
    )
    assert active.status_code == 200, active.text
    return sender_id


def _record_consent(client, status="granted", evidence="consent-form-001"):
    return client.post(
        "/v1/orgs/" + client.org_id + "/outreach/consents",
        headers=auth(), json={
            "workspace_id": client.ws_id, "contact_id": client.contact_id,
            "channel": "email", "status": status,
            "legal_basis": "consent" if status != "legitimate_interest_reviewed" else "legitimate_interest",
            "source": "website consent form",
            "evidence_reference": evidence,
            "review_note": "Founder reviewed source and scope for this contact." if status == "legitimate_interest_reviewed" else "",
        },
    )


def _create_message(client, sender_id, subject="Project discovery", contact_id=None, lead_id=None):
    response = client.post(
        "/v1/orgs/" + client.org_id + "/outreach/messages",
        headers=auth(), json={
            "workspace_id": client.ws_id, "sender_id": sender_id,
            "contact_id": contact_id or client.contact_id,
            "lead_id": client.lead_id if lead_id is None else lead_id,
            "subject": subject,
            "body": "Hello Asha, I would like to understand your team's workflow challenges.",
            "purpose": "Founder-reviewed business development follow-up",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _approve_message(client, message_id):
    submitted = client.post(
        "/v1/orgs/" + client.org_id + "/outreach/messages/" + message_id + "/submit-for-approval",
        headers=auth(),
    )
    assert submitted.status_code == 200, submitted.text
    approval_id = submitted.json()["approval_id"]
    db = client.session_factory()
    try:
        approval = db.query(Approval).filter_by(id=approval_id).one()
        approval.status = ApprovalStatus.approved
        approval.decided_by = client.user_id
        approval.decided_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()
    return approval_id


def _queue_message(client, message_id):
    approval_id = _approve_message(client, message_id)
    queued = client.post(
        "/v1/orgs/" + client.org_id + "/outreach/messages/" + message_id + "/queue",
        headers=auth(),
    )
    assert queued.status_code == 200, queued.text
    assert queued.json()["status"] == "queued"
    assert queued.json()["sent_at"] is None
    assert queued.json()["provider_message_id"] is None
    return approval_id


def test_founder_approved_outreach_queue_and_reply_stop(client):
    sender_id = _create_sender(client)
    consent = _record_consent(client)
    assert consent.status_code == 201, consent.text

    first = _create_message(client, sender_id, "First message")
    second = _create_message(client, sender_id, "Follow-up message")
    _queue_message(client, first)
    _queue_message(client, second)

    event = client.post(
        "/v1/orgs/" + client.org_id + "/outreach/messages/" + first + "/events",
        headers=auth(), json={
            "event_type": "reply", "source": "manual",
            "external_event_id": "inbound-reply-001",
            "note": "Prospect replied and asked for a meeting.",
        },
    )
    assert event.status_code == 201, event.text

    db = client.session_factory()
    try:
        first_row = db.query(OutboundMessage).filter_by(id=first).one()
        second_row = db.query(OutboundMessage).filter_by(id=second).one()
        block = db.query(CommunicationBlock).filter_by(
            contact_id=client.contact_id, channel="email",
        ).one()
        assert first_row.status == "replied"
        assert second_row.status == "cancelled"
        assert second_row.stop_reason == "reply"
        assert block.status == "active"
        assert block.reason == "reply"
    finally:
        db.close()

    blocked_message = _create_message(client, sender_id, "Another follow-up")
    blocked = client.post(
        "/v1/orgs/" + client.org_id + "/outreach/messages/" + blocked_message + "/submit-for-approval",
        headers=auth(),
    )
    assert blocked.status_code == 403

    released = client.post(
        "/v1/orgs/" + client.org_id + "/outreach/blocks/" + block.id + "/release",
        headers=auth(), json={"note": "Founder reviewed the reply and approved a new conversation."},
    )
    assert released.status_code == 200, released.text
    assert released.json()["status"] == "released"

    provider = client.post(
        "/v1/orgs/" + client.org_id + "/outreach/messages/" + first + "/events",
        headers=auth(), json={"event_type": "reply", "source": "provider"},
    )
    assert provider.status_code == 409 or provider.status_code == 403


def test_opt_out_creates_persistent_block_until_new_consent(client):
    sender_id = _create_sender(client)
    assert _record_consent(client).status_code == 201
    message_id = _create_message(client, sender_id)
    _queue_message(client, message_id)

    event = client.post(
        "/v1/orgs/" + client.org_id + "/outreach/messages/" + message_id + "/events",
        headers=auth(), json={
            "event_type": "opt_out", "source": "manual",
            "external_event_id": "unsubscribe-001", "note": "Contact requested no further email.",
        },
    )
    assert event.status_code == 201, event.text

    db = client.session_factory()
    try:
        block = db.query(CommunicationBlock).filter_by(contact_id=client.contact_id, channel="email").one()
        consent = db.query(CommunicationConsent).filter_by(contact_id=client.contact_id, channel="email").order_by(CommunicationConsent.recorded_at.desc()).first()
        assert block.status == "active" and block.reason == "opt_out"
        assert consent.status == "withdrawn"
    finally:
        db.close()

    early_release = client.post(
        "/v1/orgs/" + client.org_id + "/outreach/blocks/" + block.id + "/release",
        headers=auth(), json={"note": "Attempt without fresh consent evidence."},
    )
    assert early_release.status_code == 403

    new_consent = _record_consent(client, status="granted", evidence="new-consent-after-optout")
    assert new_consent.status_code == 201, new_consent.text
    released = client.post(
        "/v1/orgs/" + client.org_id + "/outreach/blocks/" + block.id + "/release",
        headers=auth(), json={"note": "Fresh consent evidence reviewed by founder."},
    )
    assert released.status_code == 200, released.text


def test_sender_rate_limit_workspace_isolation_and_founder_controls(client):
    sender_id = _create_sender(client, email="limited@example.test", max_per_hour=1)
    assert _record_consent(client).status_code == 201
    first = _create_message(client, sender_id, "Rate limited first")
    _queue_message(client, first)

    second = _create_message(client, sender_id, "Rate limited second")
    limited = client.post(
        "/v1/orgs/" + client.org_id + "/outreach/messages/" + second + "/submit-for-approval",
        headers=auth(),
    )
    assert limited.status_code == 429

    foreign = client.post(
        "/v1/orgs/" + client.org_id + "/outreach/messages",
        headers=auth(), json={
            "workspace_id": client.ws_id, "sender_id": sender_id,
            "contact_id": client.foreign_contact_id,
            "subject": "Foreign contact", "body": "This must not cross workspaces.",
        },
    )
    assert foreign.status_code == 404

    db = client.session_factory()
    try:
        operator = User(email="outreach-operator@example.test", display_name="Operator")
        db.add(operator)
        db.flush()
        db.add(Membership(org_id=client.org_id, user_id=operator.id, role=Role.operator))
        db.commit()
        client.app.dependency_overrides[get_principal] = lambda: Principal(user=operator)
    finally:
        db.close()

    new_sender = client.post(
        "/v1/orgs/" + client.org_id + "/outreach/senders",
        headers=auth(), json={
            "workspace_id": client.ws_id, "display_name": "Unapproved Sender",
            "email_address": "unapproved@example.test",
        },
    )
    assert new_sender.status_code == 201
    denied = client.patch(
        "/v1/orgs/" + client.org_id + "/outreach/senders/" + new_sender.json()["id"] + "/status",
        headers=auth(), json={"status": "active"},
    )
    assert denied.status_code == 403
    consent_denied = client.post(
        "/v1/orgs/" + client.org_id + "/outreach/consents",
        headers=auth(), json={
            "workspace_id": client.ws_id, "contact_id": client.contact_id,
            "channel": "email", "status": "granted", "legal_basis": "consent",
            "source": "operator", "evidence_reference": "not-authorized",
        },
    )
    assert consent_denied.status_code == 403
