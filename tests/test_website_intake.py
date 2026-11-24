import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import Principal, get_principal
from app.config import settings
from app.db import Base, get_db
from app.models import FounderAuthority, Membership, Organization, Role, User, Workspace
import app.domain_models  # noqa: F401
import app.telephony.models  # noqa: F401
import app.workforce_models  # noqa: F401
import app.operations_models  # noqa: F401


@pytest.fixture()
def website_intake_client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    db = factory()
    founder = User(email="founder@website-intake.test")
    org = Organization(name="Website Intake Test")
    db.add_all([founder, org]); db.flush()
    db.add_all([
        Membership(org_id=org.id, user_id=founder.id, role=Role.owner),
        FounderAuthority(org_id=org.id, user_id=founder.id, active=True),
    ])
    workspace = Workspace(id="website-intake-ws", org_id=org.id, name="Website Leads")
    db.add(workspace); db.commit()
    identity = {"user": founder, "org": org, "workspace": workspace}
    from app.main import app
    app.dependency_overrides.clear()
    def override_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_principal] = lambda: Principal(user=identity["user"])
    monkeypatch.setattr(settings, "website_lead_intake_enabled", True)
    monkeypatch.setattr(settings, "website_lead_intake_secret", "x" * 48)
    monkeypatch.setattr(settings, "website_lead_intake_key_id", "website-test-key-v1")
    monkeypatch.setattr(settings, "website_lead_intake_org_id", org.id)
    monkeypatch.setattr(settings, "website_lead_intake_workspace_id", workspace.id)
    client = TestClient(app)
    client.factory = factory
    client.identity = identity
    yield client
    db.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def _signed_post(client, payload, *, timestamp=None, key_id="website-test-key-v1", secret="x" * 48):
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
    ts = str(timestamp if timestamp is not None else int(time.time()))
    signature = hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).hexdigest()
    return client.post(
        "/v1/integrations/website-leads",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-AgencyOS-Timestamp": ts,
            "X-AgencyOS-Key-Id": key_id,
            "X-AgencyOS-Signature": signature,
            "Idempotency-Key": payload["submission_id"],
        },
    )


def _payload():
    return {
        "submission_id": "contact-submission-123456",
        "name": "Asha Example",
        "email": "asha@example.test",
        "company": "Example Studio",
        "project_type": "AI workflow automation",
        "budget_range": "INR 2-5 lakh",
        "timeline": "Next quarter",
        "source": "agency_website",
        "submitted_at": "2026-11-25T00:00:00Z",
    }


def test_website_lead_intake_is_signed_scoped_idempotent_and_outboxed(website_intake_client):
    from app.domain_models import Contact, Lead
    from app.telephony.models import OutboxEvent
    client = website_intake_client
    first = _signed_post(client, _payload())
    assert first.status_code == 202, first.text
    assert first.json()["accepted"] is True
    assert first.json()["duplicate"] is False
    second = _signed_post(client, _payload())
    assert second.status_code == 202, second.text
    assert second.json()["duplicate"] is True
    db = client.factory()
    try:
        leads = db.query(Lead).all()
        contacts = db.query(Contact).all()
        events = db.query(OutboxEvent).all()
        assert len(leads) == 1
        assert len(contacts) == 1
        assert len(events) == 1
        assert leads[0].workspace_id == client.identity["workspace"].id
        assert leads[0].source == "agency_website"
        assert leads[0].external_key == _payload()["submission_id"]
        assert "Asha Example" not in leads[0].qualification_notes
        assert contacts[0].consent_status == "unknown"
    finally:
        db.close()


def test_website_lead_intake_rejects_bad_signature_and_stale_timestamp(website_intake_client):
    client = website_intake_client
    bad = _signed_post(client, _payload(), secret="wrong" * 10)
    assert bad.status_code == 401
    stale = _signed_post(client, _payload(), timestamp=int(time.time()) - 3600)
    assert stale.status_code == 401


def test_website_lead_intake_rejects_body_scope_override(website_intake_client):
    payload = _payload()
    payload["workspace_id"] = "attacker-selected-workspace"
    response = _signed_post(website_intake_client, payload)
    assert response.status_code == 422


def test_website_lead_intake_disabled_is_not_public(website_intake_client, monkeypatch):
    monkeypatch.setattr(settings, "website_lead_intake_enabled", False)
    response = _signed_post(website_intake_client, _payload())
    assert response.status_code == 404
