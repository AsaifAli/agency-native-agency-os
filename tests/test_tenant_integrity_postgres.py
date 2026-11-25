"""PostgreSQL tenant-integrity regression tests for governed outreach."""
import os
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models import Approval, Organization, User, Workspace
from app.domain_models import Client, Contact, ContactActivity, Lead
from app.outreach.models import (
    CommunicationBlock,
    CommunicationConsent,
    OutboundMessage,
    OutboundMessageEvent,
    OutboundSender,
)


def test_postgres_outreach_relations_enforce_org_workspace_integrity():
    database_url = os.getenv("AGENCY_OS_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set AGENCY_OS_TEST_DATABASE_URL to run PostgreSQL tenant-integrity tests")

    parsed_url = make_url(database_url)
    assert parsed_url.get_backend_name() == "postgresql"
    assert parsed_url.database == "agency_os_worker_test", (
        "Safety check: this test may only use agency_os_worker_test"
    )

    engine = create_engine(database_url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()
    suffix = uuid.uuid4().hex[:12]

    def rejected(row):
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.add(row)
                db.flush()

    try:
        org_a = Organization(name=f"Tenant A {suffix}")
        org_b = Organization(name=f"Tenant B {suffix}")
        user = User(email=f"tenant-integrity-{suffix}@test.local", display_name="Tenant Integrity Test")
        db.add_all([org_a, org_b, user])
        db.flush()

        workspace_a = Workspace(org_id=org_a.id, name=f"Workspace A {suffix}")
        workspace_b = Workspace(org_id=org_b.id, name=f"Workspace B {suffix}")
        db.add_all([workspace_a, workspace_b])
        db.flush()

        client_b = Client(
            org_id=org_b.id, workspace_id=workspace_b.id,
            name=f"Client B {suffix}", created_by=user.id,
        )
        db.add(client_b)
        db.flush()
        contact_b = Contact(
            org_id=org_b.id, workspace_id=workspace_b.id, client_id=client_b.id,
            first_name="Contact", last_name="B", email=f"contact-{suffix}@example.test",
            created_by=user.id,
        )
        sender_a = OutboundSender(
            org_id=org_a.id, workspace_id=workspace_a.id,
            display_name="Sender A", email_address=f"sender-a-{suffix}@example.test",
            created_by=user.id,
        )
        sender_b = OutboundSender(
            org_id=org_b.id, workspace_id=workspace_b.id,
            display_name="Sender B", email_address=f"sender-b-{suffix}@example.test",
            created_by=user.id,
        )
        db.add_all([contact_b, sender_a, sender_b])
        db.flush()

        message_b = OutboundMessage(
            org_id=org_b.id, workspace_id=workspace_b.id,
            sender_id=sender_b.id, contact_id=contact_b.id,
            recipient=contact_b.email, subject="Tenant B", body="Synthetic test message",
            created_by=user.id,
        )
        db.add(message_b)
        lead_b = Lead(
            org_id=org_b.id, workspace_id=workspace_b.id,
            client_id=client_b.id, contact_id=contact_b.id,
            company_name=f"Lead B {suffix}", created_by=user.id,
        )
        db.add_all([message_b, lead_b])
        db.flush()

        rejected(Client(
            org_id=org_a.id, workspace_id=workspace_b.id,
            name="Wrong workspace client", created_by=user.id,
        ))
        rejected(Contact(
            org_id=org_a.id, workspace_id=workspace_a.id, client_id=client_b.id,
            first_name="Cross-tenant client", created_by=user.id,
        ))
        rejected(Lead(
            org_id=org_a.id, workspace_id=workspace_a.id, client_id=client_b.id,
            company_name="Cross-tenant client", created_by=user.id,
        ))
        rejected(Lead(
            org_id=org_a.id, workspace_id=workspace_a.id, contact_id=contact_b.id,
            company_name="Cross-tenant contact", created_by=user.id,
        ))
        rejected(ContactActivity(
            org_id=org_a.id, workspace_id=workspace_a.id, contact_id=contact_b.id,
            activity_type="note", subject="Cross-tenant activity", created_by=user.id,
        ))
        rejected(Contact(
            org_id=org_a.id, workspace_id=workspace_b.id,
            first_name="Wrong workspace", created_by=user.id,
        ))
        rejected(Lead(
            org_id=org_a.id, workspace_id=workspace_b.id,
            company_name="Wrong workspace", created_by=user.id,
        ))
        rejected(Approval(
            org_id=org_a.id, workspace_id=workspace_b.id,
            action_type="external_communication.sensitive",
            idempotency_key=f"approval-{suffix}", resource_id=str(uuid.uuid4()),
            requested_by=user.id,
        ))
        rejected(OutboundSender(
            org_id=org_a.id, workspace_id=workspace_b.id,
            display_name="Wrong workspace", email_address=f"wrong-{suffix}@example.test",
            created_by=user.id,
        ))
        rejected(CommunicationConsent(
            org_id=org_a.id, workspace_id=workspace_a.id, contact_id=contact_b.id,
            channel="email", status="granted", legal_basis="consent",
            source="test", evidence_reference=f"evidence-{suffix}", recorded_by=user.id,
        ))
        rejected(CommunicationBlock(
            org_id=org_a.id, workspace_id=workspace_a.id, contact_id=contact_b.id,
            channel="email", reason="manual", source="test", recorded_by=user.id,
        ))
        rejected(OutboundMessage(
            org_id=org_a.id, workspace_id=workspace_a.id,
            sender_id=sender_a.id, contact_id=contact_b.id,
            recipient=contact_b.email, subject="Cross-tenant", body="Must be rejected",
            created_by=user.id,
        ))
        rejected(OutboundMessageEvent(
            org_id=org_a.id, workspace_id=workspace_a.id, message_id=message_b.id,
            event_type="reply", source="manual", occurred_at=datetime.now(timezone.utc),
            recorded_by=user.id,
        ))
    finally:
        db.rollback()
        db.close()
        engine.dispose()
