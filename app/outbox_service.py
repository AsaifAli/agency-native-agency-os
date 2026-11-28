"""Durable, at-least-once transactional outbox delivery.

Handlers run outside database transactions. Consumers MUST deduplicate using
OutboxMessage.idempotency_key because a crash after a side effect but before
acknowledgement can cause redelivery.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Event, Thread
from typing import Callable, Mapping

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.telephony.models import OutboxEvent

# MAX_OUTBOX_ERROR_LENGTH = 1000


@dataclass(frozen=True)
class OutboxMessage:
    id: str
    org_id: str
    workspace_id: str | None
    event_type: str
    schema_version: int
    aggregate_type: str
    aggregate_id: str
    idempotency_key: str
    payload: dict
    attempts: int


OutboxHandler = Callable[[OutboxMessage], None]


class OutboxOwnershipError(RuntimeError):
    """Raised when a worker no longer owns an outbox delivery lease."""


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _safe_error(value: Exception | str) -> str:
    """Persist a safe failure classification, never raw provider error text."""
    if isinstance(value, Exception):
        error_type = type(value).__name__
    else:
        error_type = "DeliveryError"

    error_type = re.sub(r"[^A-Za-z0-9_.-]", "", error_type)[:80]
    error_type = error_type or "DeliveryError"

    return f"{error_type}: delivery handler failed"


def _lease_is_active(row: OutboxEvent, *, now: datetime | None = None) -> bool:
    """Return whether a processing row still has a live lease.

    The persisted attempt count is also the claim-generation fencing token.
    This prevents an old delivery from acting after the same worker ID reclaims
    the event and obtains a new lease.

    Normalize SQLite's naive DateTime values as UTC for deterministic tests;
    PostgreSQL DateTime(timezone=True) values remain timezone-aware.
    """
    if row.lease_expires_at is None:
        return False
    current = _utc(now or datetime.now(timezone.utc))
    return _utc(row.lease_expires_at) > current


def _message(row: OutboxEvent) -> OutboxMessage:
    return OutboxMessage(
        id=row.id,
        org_id=row.org_id,
        workspace_id=row.workspace_id,
        event_type=row.event_type,
        schema_version=row.schema_version,
        aggregate_type=row.aggregate_type,
        aggregate_id=row.aggregate_id,
        idempotency_key=row.idempotency_key,
        payload=dict(row.payload or {}),
        attempts=row.attempts,
    )


def reconcile_outbox_events(db: Session, *, limit: int = 100) -> tuple[int, int]:
    """Reconcile expired processing leases and exhausted pending rows.

    Returns (requeued, dead_lettered). Caller owns and commits transaction.
    """
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    now = datetime.now(timezone.utc)
    rows = (
        db.query(OutboxEvent)
        .filter(
            or_(
                (OutboxEvent.status == "processing") &
                OutboxEvent.lease_expires_at.is_not(None) &
                (OutboxEvent.lease_expires_at <= now),
                (OutboxEvent.status == "pending") &
                (OutboxEvent.attempts >= OutboxEvent.max_attempts),
            )
        )
        .order_by(OutboxEvent.created_at.asc(), OutboxEvent.id.asc())
        .with_for_update(skip_locked=True)
        .limit(limit)
        .all()
    )
    requeued = dead = 0
    for row in rows:
        row.claimed_by = None
        row.lease_expires_at = None
        if row.attempts >= row.max_attempts:
            row.status = "dead_letter"
            dead += 1
        else:
            row.status = "pending"
            row.available_at = now
            requeued += 1
    if rows:
        db.flush()
    return requeued, dead


def claim_outbox_batch(
    db: Session,
    *,
    worker_id: str,
    event_types: set[str],
    limit: int = 25,
    lease_seconds: int = 120,
) -> list[OutboxMessage]:
    """Claim deliverable rows using row locks; caller commits before handlers."""
    if not worker_id or len(worker_id) > 160:
        raise ValueError("worker_id must contain 1-160 characters")
    if not 1 <= limit <= 250:
        raise ValueError("limit must be between 1 and 250")
    if not 15 <= lease_seconds <= 3600:
        raise ValueError("lease_seconds must be between 15 and 3600")
    if not event_types:
        return []

    now = datetime.now(timezone.utc)
    rows = (
        db.query(OutboxEvent)
        .filter(
            OutboxEvent.event_type.in_(event_types),
            or_(
                (OutboxEvent.status == "pending") & (OutboxEvent.available_at <= now),
                (OutboxEvent.status == "processing") &
                OutboxEvent.lease_expires_at.is_not(None) &
                (OutboxEvent.lease_expires_at <= now),
            ),
        )
        .order_by(OutboxEvent.available_at.asc(), OutboxEvent.created_at.asc(), OutboxEvent.id.asc())
        .with_for_update(skip_locked=True)
        .limit(limit)
        .all()
    )

    claimed: list[OutboxMessage] = []
    for row in rows:
        if row.attempts >= row.max_attempts:
            row.status = "dead_letter"
            row.claimed_by = None
            row.lease_expires_at = None
            continue
        row.status = "processing"
        row.attempts += 1
        row.claimed_by = worker_id
        row.lease_expires_at = now + timedelta(seconds=lease_seconds)
        claimed.append(_message(row))
    if rows:
        db.flush()
    return claimed


def _renew_lease(
    session_factory, *, message: OutboxMessage, worker_id: str, lease_seconds: int,
) -> bool:
    """Extend only the still-live lease for this exact delivery generation."""
    if not 15 <= lease_seconds <= 3600:
        raise ValueError("lease_seconds must be between 15 and 3600")
    now = datetime.now(timezone.utc)
    with session_factory() as db:
        updated = (
            db.query(OutboxEvent)
            .filter(
                OutboxEvent.id == message.id,
                OutboxEvent.status == "processing",
                OutboxEvent.claimed_by == worker_id,
                OutboxEvent.attempts == message.attempts,
                OutboxEvent.lease_expires_at.is_not(None),
                OutboxEvent.lease_expires_at > now,
            )
            .update(
                {OutboxEvent.lease_expires_at: now + timedelta(seconds=lease_seconds)},
                synchronize_session=False,
            )
        )
        db.commit()
        return updated == 1


class _OutboxLeaseHeartbeat:
    """Renew a delivery lease while its handler runs, using independent sessions."""

    def __init__(
        self, session_factory, *, message: OutboxMessage, worker_id: str,
        lease_seconds: int, interval_seconds: float,
    ) -> None:
        self.session_factory = session_factory
        self.message = message
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        self.interval_seconds = interval_seconds
        self._stop = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        self._thread = Thread(
            target=self._run,
            name=f"outbox-lease-{self.message.id[:8]}",
            daemon=True,
        )
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                if not _renew_lease(
                    self.session_factory,
                    message=self.message,
                    worker_id=self.worker_id,
                    lease_seconds=self.lease_seconds,
                ):
                    return
            except Exception:
                # The final ack/failure operation performs the authoritative
                # ownership check. If renewal could not be confirmed, never
                # bypass that check or assume the lease is still ours.
                return

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(5.0, self.interval_seconds * 2))
            if self._thread.is_alive():
                raise RuntimeError("Outbox lease heartbeat did not stop cleanly")


def _acknowledge(session_factory, *, message: OutboxMessage, worker_id: str) -> None:
    with session_factory() as db:
        row = db.query(OutboxEvent).filter(OutboxEvent.id == message.id).with_for_update().one_or_none()
        if (
            row is None
            or row.status != "processing"
            or row.claimed_by != worker_id
            or row.attempts != message.attempts
            or not _lease_is_active(row)
        ):
            raise OutboxOwnershipError("Outbox delivery lease is no longer owned by this worker")
        row.status = "published"
        row.published_at = datetime.now(timezone.utc)
        row.claimed_by = None
        row.lease_expires_at = None
        row.last_error = None
        db.commit()


def _record_failure(
    session_factory, *, message: OutboxMessage, worker_id: str,
    error: Exception, base_retry_seconds: int, max_retry_seconds: int,
) -> bool:
    with session_factory() as db:
        row = db.query(OutboxEvent).filter(OutboxEvent.id == message.id).with_for_update().one_or_none()
        if (
            row is None
            or row.status != "processing"
            or row.claimed_by != worker_id
            or row.attempts != message.attempts
            or not _lease_is_active(row)
        ):
            # The lease expired or ownership changed; stale workers cannot mutate it.
            return False
        row.last_error = _safe_error(error)
        row.claimed_by = None
        row.lease_expires_at = None
        if row.attempts >= row.max_attempts:
            row.status = "dead_letter"
        else:
            delay = base_retry_seconds

            for _ in range(max(row.attempts - 1, 0)):
                if delay >= max_retry_seconds:
                    break
                delay = min(delay * 2, max_retry_seconds)
            row.status = "pending"
            row.available_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
        db.commit()
        return True


def dispatch_outbox_batch(
    session_factory,
    *,
    worker_id: str,
    handlers: Mapping[str, OutboxHandler],
    limit: int = 25,
    lease_seconds: int = 120,
    heartbeat_interval_seconds: float | None = None,
    base_retry_seconds: int = 15,
    max_retry_seconds: int = 3600,
) -> tuple[int, int, int]:
    """Claim, deliver outside transactions, then acknowledge or retry.

    Returns (published, retried, dead_lettered). Unknown event types are not
    claimed. Handler side effects must use the message idempotency key.
    """
    if not handlers:
        return 0, 0, 0
    if base_retry_seconds < 1 or max_retry_seconds < base_retry_seconds:
        raise ValueError("Invalid outbox retry delay bounds")
    if not 15 <= lease_seconds <= 3600:
        raise ValueError("lease_seconds must be between 15 and 3600")
    if heartbeat_interval_seconds is None:
        heartbeat_interval_seconds = min(30.0, lease_seconds / 3.0)
    if not 0 < heartbeat_interval_seconds <= lease_seconds / 3.0:
        raise ValueError("heartbeat_interval_seconds must be positive and no more than one-third of the lease")

    with session_factory() as db:
        messages = claim_outbox_batch(
            db, worker_id=worker_id, event_types=set(handlers),
            limit=limit, lease_seconds=lease_seconds,
        )
        db.commit()

    published = retried = dead = 0
    for message in messages:
        heartbeat = _OutboxLeaseHeartbeat(
            session_factory,
            message=message,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
            interval_seconds=heartbeat_interval_seconds,
        )
        heartbeat.start()
        try:
            try:
                handlers[message.event_type](message)
            except OutboxOwnershipError:
                # A handler that detects lost ownership must not mutate the event.
                continue
            except Exception as exc:
                recorded = _record_failure(
                    session_factory, message=message, worker_id=worker_id,
                    error=exc, base_retry_seconds=base_retry_seconds,
                    max_retry_seconds=max_retry_seconds,
                )
                if not recorded:
                    continue
                # Count based on the persisted state, not the exception type.
                with session_factory() as db:
                    row = db.query(OutboxEvent).filter_by(id=message.id).one_or_none()
                    if row is not None and row.status == "dead_letter":
                        dead += 1
                    else:
                        retried += 1
            else:
                try:
                    _acknowledge(session_factory, message=message, worker_id=worker_id)
                except OutboxOwnershipError:
                    continue
                published += 1
        finally:
            heartbeat.stop()
    return published, retried, dead



def summarize_outbox(
    db: Session, *, org_id: str, workspace_id: str,
    now: datetime | None = None,
) -> dict:
    """Return payload-free operational counts for one exact tenant workspace."""
    from sqlalchemy import func

    now = _utc(now or datetime.now(timezone.utc))
    scope = (OutboxEvent.org_id == org_id, OutboxEvent.workspace_id == workspace_id)
    grouped = (
        db.query(OutboxEvent.status, func.count(OutboxEvent.id))
        .filter(*scope)
        .group_by(OutboxEvent.status)
        .all()
    )
    counts = {status: 0 for status in ("pending", "processing", "published", "dead_letter")}
    for status, count in grouped:
        if status in counts:
            counts[status] = int(count)

    oldest_pending = (
        db.query(func.min(OutboxEvent.created_at))
        .filter(*scope, OutboxEvent.status == "pending")
        .scalar()
    )
    expired_leases = (
        db.query(func.count(OutboxEvent.id))
        .filter(
            *scope,
            OutboxEvent.status == "processing",
            OutboxEvent.lease_expires_at.is_not(None),
            OutboxEvent.lease_expires_at <= now,
        )
        .scalar()
    )
    exhausted_pending = (
        db.query(func.count(OutboxEvent.id))
        .filter(
            *scope,
            OutboxEvent.status == "pending",
            OutboxEvent.attempts >= OutboxEvent.max_attempts,
        )
        .scalar()
    )
    oldest_pending_utc = _utc(oldest_pending) if oldest_pending else None
    age = max(0, int((now - oldest_pending_utc).total_seconds())) if oldest_pending_utc else None
    expired_lease_count = int(expired_leases or 0)
    dead_letter_count = counts["dead_letter"]
    thresholds = {
        "pending_age_warning_seconds": settings.outbox_pending_age_warning_seconds,
        "expired_lease_warning_count": settings.outbox_expired_lease_warning_count,
        "dead_letter_warning_count": settings.outbox_dead_letter_warning_count,
    }
    alerts = []
    if age is not None and age >= thresholds["pending_age_warning_seconds"]:
        alerts.append("pending_age_exceeded")
    if expired_lease_count >= thresholds["expired_lease_warning_count"]:
        alerts.append("expired_leases_detected")
    if dead_letter_count >= thresholds["dead_letter_warning_count"]:
        alerts.append("dead_letter_threshold_exceeded")
    return {
        "health": "warning" if alerts else "healthy",
        "alerts": alerts,
        "thresholds": thresholds,
        "counts": counts,
        "total": sum(counts.values()),
        "oldest_pending_at": oldest_pending_utc.isoformat() if oldest_pending_utc else None,
        "oldest_pending_age_seconds": age,
        "expired_leases": expired_lease_count,
        "exhausted_pending": int(exhausted_pending or 0),
        "as_of": now.isoformat(),
    }
