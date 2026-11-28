"""Regression tests for expired outbox ownership, including same-ID worker reuse."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.domain_models import Lead  # noqa: F401 — register shared metadata
from app.models import Organization, Workspace
from app.telephony.models import OutboxEvent
from app.outbox_service import (
    OutboxMessage,
    OutboxOwnershipError,
    _acknowledge,
    _record_failure,
)


@pytest.fixture
def lease_context(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'outbox-lease-ownership.db'}",
        connect_args={"check_same_thread": False},
    )
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    db = Session()
    suffix = uuid.uuid4().hex[:10]
    org = Organization(name=f"Lease Org {suffix}")
    db.add(org)
    db.flush()
    workspace = Workspace(id=f"lease-ws-{suffix}", org_id=org.id, name="Lease Workspace")
    db.add(workspace)
    db.flush()
    event = OutboxEvent(
        org_id=org.id,
        workspace_id=workspace.id,
        event_type="test.event",
        schema_version=1,
        aggregate_type="test",
        aggregate_id=str(uuid.uuid4()),
        idempotency_key=f"test:{uuid.uuid4().hex}",
        payload={"safe": True},
        status="processing",
        attempts=1,
        claimed_by="reused-worker-id",
        lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=5),
    )
    db.add(event)
    db.commit()
    message = OutboxMessage(
        id=event.id,
        org_id=org.id,
        workspace_id=workspace.id,
        event_type=event.event_type,
        schema_version=event.schema_version,
        aggregate_type=event.aggregate_type,
        aggregate_id=event.aggregate_id,
        idempotency_key=event.idempotency_key,
        payload=dict(event.payload),
        attempts=event.attempts,
    )
    try:
        yield Session, db, event.id, message
    finally:
        db.rollback()
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_expired_owner_cannot_ack_even_if_worker_id_was_reused(lease_context):
    Session, db, event_id, message = lease_context

    with pytest.raises(OutboxOwnershipError):
        _acknowledge(Session, message=message, worker_id="reused-worker-id")

    db.expire_all()
    row = db.query(OutboxEvent).filter_by(id=event_id).one()
    assert row.status == "processing"
    assert row.claimed_by == "reused-worker-id"


def test_expired_owner_cannot_record_failure_even_if_worker_id_was_reused(lease_context):
    Session, db, event_id, message = lease_context

    _record_failure(
        Session,
        message=message,
        worker_id="reused-worker-id",
        error=RuntimeError("synthetic failure"),
        base_retry_seconds=1,
        max_retry_seconds=2,
    )

    db.expire_all()
    row = db.query(OutboxEvent).filter_by(id=event_id).one()
    assert row.status == "processing"
    assert row.claimed_by == "reused-worker-id"
    assert row.last_error is None
