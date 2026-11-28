import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.domain_models import Lead  # Register leads table in shared metadata.
from app.models import Organization, Workspace
from app.telephony.models import OutboxEvent
from app.outbox_service import (
    claim_outbox_batch,
    dispatch_outbox_batch,
    reconcile_outbox_events,
)


@pytest.fixture
def outbox_context(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'outbox-tests.db'}",
        connect_args={"check_same_thread": False},
    )
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    db = Session()
    suffix = uuid.uuid4().hex[:10]
    org = Organization(name=f"Outbox Org {suffix}")
    db.add(org)
    db.flush()
    workspace = Workspace(id=f"outbox-ws-{suffix}", org_id=org.id, name="Outbox Workspace")
    db.add(workspace)
    db.commit()
    try:
        yield {"db": db, "Session": Session, "org_id": org.id, "workspace_id": workspace.id}
    finally:
        db.rollback()
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def add_event(ctx, **overrides):
    values = {
        "org_id": ctx["org_id"],
        "workspace_id": ctx["workspace_id"],
        "event_type": "test.event",
        "schema_version": 1,
        "aggregate_type": "test",
        "aggregate_id": str(uuid.uuid4()),
        "idempotency_key": f"test:{uuid.uuid4().hex}",
        "payload": {"safe": True},
    }
    values.update(overrides)
    row = OutboxEvent(**values)
    ctx["db"].add(row)
    ctx["db"].commit()
    return row.id


def test_claim_is_scoped_to_registered_event_types_and_sets_lease(outbox_context):
    ctx = outbox_context
    event_id = add_event(ctx)
    messages = claim_outbox_batch(
        ctx["db"], worker_id="outbox-worker-1", event_types={"test.event"},
        limit=10, lease_seconds=60,
    )
    ctx["db"].commit()
    assert [m.id for m in messages] == [event_id]
    row = ctx["db"].query(OutboxEvent).filter_by(id=event_id).one()
    assert row.status == "processing"
    assert row.attempts == 1
    assert row.claimed_by == "outbox-worker-1"
    assert row.lease_expires_at is not None


def test_unknown_event_type_is_not_claimed(outbox_context):
    ctx = outbox_context
    event_id = add_event(ctx)
    assert claim_outbox_batch(
        ctx["db"], worker_id="worker", event_types={"unhandled.event"}
    ) == []
    row = ctx["db"].query(OutboxEvent).filter_by(id=event_id).one()
    assert row.status == "pending"
    assert row.attempts == 0


def test_dispatch_marks_success_published_and_passes_idempotency_key(outbox_context):
    ctx = outbox_context
    event_id = add_event(ctx)
    received = []
    result = dispatch_outbox_batch(
        ctx["Session"], worker_id="worker-success",
        handlers={"test.event": lambda message: received.append(message.idempotency_key)},
    )
    row = ctx["db"].query(OutboxEvent).filter_by(id=event_id).one()
    assert result == (1, 0, 0)
    assert received == [row.idempotency_key]
    assert row.status == "published"
    assert row.published_at is not None
    assert row.claimed_by is None


def test_dispatch_failure_retries_and_redacts_credentials(outbox_context):
    ctx = outbox_context
    event_id = add_event(ctx)

    def fail(_message):
        raise RuntimeError("provider failed Bearer supersecret api_key=abc123")

    result = dispatch_outbox_batch(
        ctx["Session"], worker_id="worker-fail", handlers={"test.event": fail},
        base_retry_seconds=1, max_retry_seconds=2,
    )
    row = ctx["db"].query(OutboxEvent).filter_by(id=event_id).one()
    assert result == (0, 1, 0)
    assert row.status == "pending"
    assert "supersecret" not in row.last_error
    assert "abc123" not in row.last_error
    assert row.last_error == "RuntimeError: delivery handler failed"
    assert "provider failed" not in row.last_error
    available_at = row.available_at
    if available_at.tzinfo is None:
        available_at = available_at.replace(tzinfo=timezone.utc)
    assert available_at > datetime.now(timezone.utc) - timedelta(seconds=1)


def test_exhausted_delivery_moves_to_dead_letter(outbox_context):
    ctx = outbox_context
    event_id = add_event(ctx, max_attempts=1)
    result = dispatch_outbox_batch(
        ctx["Session"], worker_id="worker-dead", handlers={
            "test.event": lambda _message: (_ for _ in ()).throw(RuntimeError("no"))
        },
    )
    row = ctx["db"].query(OutboxEvent).filter_by(id=event_id).one()
    assert result == (0, 0, 1)
    assert row.status == "dead_letter"
    assert row.attempts == 1


def test_reconcile_requeues_expired_processing_lease(outbox_context):
    ctx = outbox_context
    event_id = add_event(ctx)
    row = ctx["db"].query(OutboxEvent).filter_by(id=event_id).one()
    row.status = "processing"
    row.claimed_by = "crashed-worker"
    row.attempts = 1
    row.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=5)
    ctx["db"].commit()

    assert reconcile_outbox_events(ctx["db"], limit=10) == (1, 0)
    ctx["db"].commit()
    assert row.status == "pending"
    assert row.claimed_by is None
    assert row.lease_expires_at is None

def test_outbox_model_declares_lease_recovery_index():
    index_names = {
        index.name
        for index in OutboxEvent.__table__.indexes
    }

    assert "ix_outbox_dispatch" in index_names
    assert "ix_outbox_lease_recovery" in index_names


def test_outbox_summary_is_workspace_scoped_and_never_returns_payload(outbox_context):
    from app.outbox_service import summarize_outbox

    ctx = outbox_context
    now = datetime.now(timezone.utc)
    add_event(ctx, payload={"secret": "must-not-leak"}, created_at=now - timedelta(seconds=90))
    add_event(ctx, status="published")

    other_workspace = Workspace(
        id=f"other-{uuid.uuid4().hex[:10]}", org_id=ctx["org_id"],
        name="Other Workspace",
    )
    ctx["db"].add(other_workspace)
    ctx["db"].commit()
    add_event({
        **ctx, "workspace_id": other_workspace.id,
    }, payload={"other_workspace": True})

    summary = summarize_outbox(
        ctx["db"], org_id=ctx["org_id"], workspace_id=ctx["workspace_id"], now=now,
    )
    assert summary["counts"] == {
        "pending": 1, "processing": 0, "published": 1, "dead_letter": 0,
    }
    assert summary["total"] == 2
    assert summary["oldest_pending_age_seconds"] == 90
    assert "payload" not in summary
    assert "secret" not in str(summary)
    assert "other_workspace" not in str(summary)


def test_outbox_summary_reports_expired_and_exhausted_work(outbox_context):
    from app.outbox_service import summarize_outbox

    ctx = outbox_context
    add_event(ctx, status="processing", claimed_by="stale-worker",
              lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=10))
    add_event(ctx, attempts=8, max_attempts=8)
    summary = summarize_outbox(
        ctx["db"], org_id=ctx["org_id"], workspace_id=ctx["workspace_id"],
        now=datetime.now(timezone.utc),
    )
    assert summary["expired_leases"] == 1
    assert summary["exhausted_pending"] == 1

def test_dispatch_renews_lease_during_long_running_handler(outbox_context):
    import time

    ctx = outbox_context
    event_id = add_event(ctx)

    def long_handler(_message):
        # Force the lease close to expiry while the handler is still active.
        with ctx["Session"]() as db:
            row = db.query(OutboxEvent).filter_by(id=event_id).one()
            row.lease_expires_at = datetime.now(timezone.utc) + timedelta(seconds=0.1)
            db.commit()
        time.sleep(0.25)

    result = dispatch_outbox_batch(
        ctx["Session"],
        worker_id="worker-long-handler",
        handlers={"test.event": long_handler},
        lease_seconds=15,
        heartbeat_interval_seconds=0.02,
    )

    row = ctx["db"].query(OutboxEvent).filter_by(id=event_id).one()
    assert result == (1, 0, 0)
    assert row.status == "published"


def test_outbox_summary_evaluates_configurable_warning_thresholds(outbox_context, monkeypatch):
    from app.config import settings
    from app.outbox_service import summarize_outbox

    ctx = outbox_context
    now = datetime.now(timezone.utc)
    add_event(
        ctx,
        created_at=now - timedelta(seconds=120),
    )
    add_event(
        ctx,
        status="processing",
        claimed_by="expired-worker",
        lease_expires_at=now - timedelta(seconds=5),
    )
    add_event(ctx, status="dead_letter", attempts=3, max_attempts=3)

    monkeypatch.setattr(settings, "outbox_pending_age_warning_seconds", 60)
    monkeypatch.setattr(settings, "outbox_expired_lease_warning_count", 1)
    monkeypatch.setattr(settings, "outbox_dead_letter_warning_count", 1)

    summary = summarize_outbox(
        ctx["db"], org_id=ctx["org_id"], workspace_id=ctx["workspace_id"], now=now,
    )

    assert summary["health"] == "warning"
    assert summary["alerts"] == [
        "pending_age_exceeded",
        "expired_leases_detected",
        "dead_letter_threshold_exceeded",
    ]
    assert summary["thresholds"] == {
        "pending_age_warning_seconds": 60,
        "expired_lease_warning_count": 1,
        "dead_letter_warning_count": 1,
    }


def test_outbox_summary_warns_when_pending_events_have_exhausted_attempts(outbox_context, monkeypatch):
    from app.config import settings
    from app.outbox_service import summarize_outbox

    ctx = outbox_context
    add_event(ctx, attempts=4, max_attempts=4)
    monkeypatch.setattr(settings, "outbox_pending_age_warning_seconds", 900)
    monkeypatch.setattr(settings, "outbox_expired_lease_warning_count", 10)
    monkeypatch.setattr(settings, "outbox_dead_letter_warning_count", 10)
    monkeypatch.setattr(settings, "outbox_exhausted_pending_warning_count", 1)

    summary = summarize_outbox(
        ctx["db"], org_id=ctx["org_id"], workspace_id=ctx["workspace_id"],
        now=datetime.now(timezone.utc),
    )

    assert summary["health"] == "warning"
    assert summary["alerts"] == ["exhausted_pending_detected"]
    assert summary["exhausted_pending"] == 1
    assert summary["thresholds"]["exhausted_pending_warning_count"] == 1
