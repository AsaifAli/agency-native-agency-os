
import logging
import time
from threading import Event
from typing import Callable

from sqlalchemy.orm import Session

from app.config import settings
from app.db import WorkerSessionLocal
from app.worker.processor import process_one_execution
from app.machine_identity import expire_due_agent_sessions
from app.browser_sessions import prune_expired_browser_sessions
from app.outbox_handlers import OUTBOX_HANDLERS
from app.outbox_service import dispatch_outbox_batch, reconcile_outbox_events
from app.worker_service import (
    promote_due_retries,
    recover_expired_execution_leases,
    queue_ready_delegations,
)

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]
ExecutionProcessor = Callable[..., str | None]


def _run_maintenance(
    session_factory: SessionFactory,
    batch_size: int,
) -> tuple[int, int, int]:
    """Run retry promotion and lease recovery in separate transactions."""

    with session_factory() as db:
        promoted_count = promote_due_retries(
            db,
            limit=batch_size,
        )
        db.commit()

    with session_factory() as db:
        recovered_count = recover_expired_execution_leases(
            db,
            limit=batch_size,
        )
        queued_delegations = queue_ready_delegations(
            db,
            limit=batch_size,
        )
        db.commit()

    return promoted_count, recovered_count, queued_delegations


def _run_session_maintenance(
    session_factory: SessionFactory,
    batch_size: int,
) -> int:
    """Expire due machine sessions in a separate committed maintenance transaction."""
    with session_factory() as db:
        expired_count = expire_due_agent_sessions(db, limit=batch_size)
        db.commit()
    return expired_count


def _run_browser_session_retention(session_factory: SessionFactory, batch_size: int) -> int:
    """Prune a bounded batch of expired browser sessions and audit the deletion."""
    with session_factory() as db:
        deleted = prune_expired_browser_sessions(
            db, retention_days=settings.browser_session_retention_days,
            limit=min(batch_size, 1000),
        )
        db.commit()
    return deleted


def _run_outbox_maintenance(
    session_factory: SessionFactory,
    *,
    worker_id: str,
    batch_size: int,
) -> tuple[int, int, int, int]:
    """Always reconcile durable outbox state; dispatch only registered types."""
    with session_factory() as db:
        requeued, dead_lettered = reconcile_outbox_events(
            db, limit=batch_size
        )
        db.commit()

    if not OUTBOX_HANDLERS:
        return 0, 0, dead_lettered, requeued

    published, retried, dispatched_dead = dispatch_outbox_batch(
        session_factory,
        worker_id=worker_id,
        handlers=OUTBOX_HANDLERS,
        limit=min(batch_size, 250),
        lease_seconds=settings.outbox_lease_seconds,
        base_retry_seconds=settings.outbox_base_retry_seconds,
        max_retry_seconds=settings.outbox_max_retry_seconds,
    )
    return published, retried, dead_lettered + dispatched_dead, requeued


def run_worker(
    stop_event: Event,
    worker_id: str,
    session_factory: SessionFactory = WorkerSessionLocal,
    processor: ExecutionProcessor = process_one_execution,
    lease_seconds: int | None = None,
    poll_interval_seconds: float | None = None,
    maintenance_interval_seconds: int | None = None,
    maintenance_batch_size: int | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Run the worker polling loop until a stop signal is received."""

    if not isinstance(worker_id, str) or not worker_id.strip():
        raise ValueError("worker_id must be a non-empty string")

    if len(worker_id) > 160:
        raise ValueError("worker_id must be 160 characters or fewer")

    lease_seconds = (
        settings.worker_lease_seconds
        if lease_seconds is None
        else lease_seconds
    )
    poll_interval_seconds = (
        settings.worker_poll_interval_seconds
        if poll_interval_seconds is None
        else poll_interval_seconds
    )
    maintenance_interval_seconds = (
        settings.worker_maintenance_interval_seconds
        if maintenance_interval_seconds is None
        else maintenance_interval_seconds
    )
    maintenance_batch_size = (
        settings.worker_maintenance_batch_size
        if maintenance_batch_size is None
        else maintenance_batch_size
    )

    if not 15 <= lease_seconds <= 3600:
        raise ValueError("lease_seconds must be between 15 and 3600")

    if not 0.1 <= poll_interval_seconds <= 60:
        raise ValueError(
            "poll_interval_seconds must be between 0.1 and 60"
        )

    if maintenance_interval_seconds < 1:
        raise ValueError(
            "maintenance_interval_seconds must be at least 1"
        )

    if not 1 <= maintenance_batch_size <= 1000:
        raise ValueError(
            "maintenance_batch_size must be between 1 and 1000"
        )

    next_maintenance_at = 0.0

    logger.info("Worker started: worker_id=%s", worker_id)

    while not stop_event.is_set():
        now = clock()

        if now >= next_maintenance_at:
            promoted, recovered, queued_delegations = _run_maintenance(
                session_factory=session_factory,
                batch_size=maintenance_batch_size,
            )

            if promoted or recovered or queued_delegations:
                logger.info(
                    "Worker maintenance completed: "
                    "promoted=%s recovered=%s delegated_queued=%s",
                    promoted,
                    recovered,
                    queued_delegations,
                )

            expired_sessions = _run_session_maintenance(
                session_factory=session_factory,
                batch_size=maintenance_batch_size,
            )
            if expired_sessions:
                logger.info("Expired agent sessions: count=%s", expired_sessions)

            pruned_browser_sessions = _run_browser_session_retention(
                session_factory=session_factory, batch_size=maintenance_batch_size,
            )
            if pruned_browser_sessions:
                logger.info("Pruned retained browser sessions: count=%s", pruned_browser_sessions)

            published, retried, dead_lettered, requeued = _run_outbox_maintenance(
                session_factory=session_factory,
                worker_id=worker_id,
                batch_size=maintenance_batch_size,
            )
            if published or retried or dead_lettered or requeued:
                logger.info(
                    "Outbox maintenance completed: published=%s retried=%s "
                    "dead_lettered=%s requeued=%s",
                    published, retried, dead_lettered, requeued,
                )

            next_maintenance_at = (
                clock() + maintenance_interval_seconds
            )

        if stop_event.is_set():
            break

        execution_id = processor(
            worker_id=worker_id,
            lease_seconds=lease_seconds,
            session_factory=session_factory,
        )

        if execution_id is None:
            stop_event.wait(poll_interval_seconds)

    logger.info("Worker stopping: worker_id=%s", worker_id)
