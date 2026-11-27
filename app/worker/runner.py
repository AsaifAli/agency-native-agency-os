import logging
import time
from threading import Event, Thread
from typing import Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import (
    WorkerSessionLocal,
    worker_engine,
    verify_postgres_role,
    scoped_worker_workspace_session_factory,
)
from app.worker.processor import process_one_execution
from app.machine_identity import expire_due_agent_sessions
from app.retention import purge_due_retention_data
from app.outbox_handlers import OUTBOX_HANDLERS
from app.outbox_service import dispatch_outbox_batch, reconcile_outbox_events
from app.worker_service import (
    promote_due_retries,
    recover_expired_execution_leases,
    queue_ready_delegations,
    claim_worker_maintenance_scope,
)

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]
ExecutionProcessor = Callable[..., str | None]


def _verify_worker_database_role() -> None:
    """Verify the dedicated NOBYPASSRLS role before production worker startup."""
    if settings.app_env.lower() != "production":
        return
    if settings.process_role != "worker":
        raise RuntimeError("Worker process must use PROCESS_ROLE=worker in production")
    if worker_engine.dialect.name != "postgresql":
        raise RuntimeError("Production worker execution requires PostgreSQL")
    verify_postgres_role(
        worker_engine,
        expected_bypassrls=False,
        require_rls=True,
        expected_role="agency_os_worker",
    )


def _run_maintenance(
    session_factory: SessionFactory,
    batch_size: int,
) -> tuple[int, int, int]:
    """Run maintenance only inside the supplied organization/workspace scope."""
    with session_factory() as db:
        promoted_count = promote_due_retries(db, limit=batch_size)
        db.commit()

    with session_factory() as db:
        recovered_count = recover_expired_execution_leases(db, limit=batch_size)
        queued_delegations = queue_ready_delegations(db, limit=batch_size)
        db.commit()

    return promoted_count, recovered_count, queued_delegations


def _run_session_maintenance(
    session_factory: SessionFactory,
    batch_size: int,
) -> int:
    """Expire machine sessions only within the selected workspace."""
    with session_factory() as db:
        expired_count = expire_due_agent_sessions(db, limit=batch_size)
        db.commit()
    return expired_count


def _run_retention_maintenance(
    session_factory: SessionFactory,
    batch_size: int,
) -> dict[str, int]:
    """Scrub eligible session descriptions and tool payloads in one workspace."""
    with session_factory() as db:
        result = purge_due_retention_data(
            db,
            limit=min(batch_size, 1000),
            agent_session_days=settings.agent_session_metadata_retention_days,
            tool_invocation_payload_days=settings.tool_invocation_payload_retention_days,
        )
        db.commit()
    return result


def _run_browser_session_retention(
    session_factory: SessionFactory,
    batch_size: int,
) -> int:
    """Run the bounded SECURITY DEFINER retention operation; no table-wide bypass."""
    with session_factory() as db:
        deleted = db.execute(
            text(
                "SELECT agency_os_private.prune_expired_browser_sessions("
                ":retention_days, :batch_size)"
            ),
            {
                "retention_days": settings.browser_session_retention_days,
                "batch_size": min(batch_size, 1000),
            },
        ).scalar_one()
        db.commit()
    return int(deleted)


def _run_outbox_maintenance(
    session_factory: SessionFactory,
    *,
    worker_id: str,
    batch_size: int,
) -> tuple[int, int, int, int]:
    """Reconcile and dispatch only events visible in the selected workspace."""
    with session_factory() as db:
        requeued, dead_lettered = reconcile_outbox_events(db, limit=batch_size)
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


class MaintenanceLeaseHeartbeat:
    """Keep a workspace capability alive while bounded maintenance runs."""

    def __init__(self, session_factory: SessionFactory, lease_seconds: int) -> None:
        self.session_factory = session_factory
        self.lease_seconds = lease_seconds
        self.interval_seconds = min(30.0, lease_seconds / 3)
        self._stop = Event()
        self._thread: Thread | None = None
        self._error: Exception | None = None

    def start(self) -> None:
        self._thread = Thread(
            target=self._run, name="worker-maintenance-lease-heartbeat", daemon=True,
        )
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                with self.session_factory() as db:
                    renewed = db.execute(text(
                        "SELECT agency_os_private.renew_worker_maintenance_scope(:lease_seconds)"
                    ), {"lease_seconds": self.lease_seconds}).scalar_one()
                    if renewed is not True:
                        raise RuntimeError("Worker maintenance capability could not be renewed")
                    db.commit()
            except Exception as exc:
                self._error = exc
                self._stop.set()
                return

    def assert_healthy(self) -> None:
        if self._error is not None:
            raise RuntimeError("Worker maintenance lease renewal failed") from self._error

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(5.0, self.interval_seconds))
            if self._thread.is_alive():
                raise RuntimeError("Worker maintenance heartbeat did not stop cleanly")


def _release_maintenance_scope(session_factory: SessionFactory) -> None:
    """Release the current workspace lease after all bounded maintenance work."""
    with session_factory() as db:
        released = db.execute(text(
            "SELECT agency_os_private.release_worker_maintenance_scope()"
        )).scalar_one()
        if released is not True:
            raise RuntimeError("Worker maintenance lease could not be released")
        db.commit()


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
    """Process executions globally; maintenance uses one leased workspace at a time."""
    if not isinstance(worker_id, str) or not worker_id.strip():
        raise ValueError("worker_id must be a non-empty string")
    if len(worker_id) > 160:
        raise ValueError("worker_id must be 160 characters or fewer")

    lease_seconds = settings.worker_lease_seconds if lease_seconds is None else lease_seconds
    poll_interval_seconds = settings.worker_poll_interval_seconds if poll_interval_seconds is None else poll_interval_seconds
    maintenance_interval_seconds = settings.worker_maintenance_interval_seconds if maintenance_interval_seconds is None else maintenance_interval_seconds
    maintenance_batch_size = settings.worker_maintenance_batch_size if maintenance_batch_size is None else maintenance_batch_size

    if not 15 <= lease_seconds <= 3600:
        raise ValueError("lease_seconds must be between 15 and 3600")
    if not 0.1 <= poll_interval_seconds <= 60:
        raise ValueError("poll_interval_seconds must be between 0.1 and 60")
    if maintenance_interval_seconds < 1:
        raise ValueError("maintenance_interval_seconds must be at least 1")
    if not 1 <= maintenance_batch_size <= 1000:
        raise ValueError("maintenance_batch_size must be between 1 and 1000")

    _verify_worker_database_role()

    next_maintenance_at = 0.0
    logger.info("Worker started: worker_id=%s", worker_id)

    while not stop_event.is_set():
        did_work = False
        now = clock()

        if now >= next_maintenance_at:
            cursor_workspace_id = None
            totals = [0, 0, 0, 0, 0, 0, 0, 0, 0]
            while not stop_event.is_set():
                # The database chooses exactly one workspace. The worker never
                # receives an unscoped tenant inventory or chooses a tenant ID.
                with session_factory() as claim_db:
                    capability = claim_worker_maintenance_scope(
                        claim_db, worker_id=worker_id,
                        after_workspace_id=cursor_workspace_id,
                    )
                    claim_db.commit()
                if capability is None:
                    break

                scoped_factory = scoped_worker_workspace_session_factory(
                    capability, session_factory,
                )
                lease_heartbeat = MaintenanceLeaseHeartbeat(
                    scoped_factory, capability.lease_seconds,
                )
                lease_heartbeat.start()
                try:
                    promoted, recovered, queued = _run_maintenance(
                        scoped_factory, maintenance_batch_size,
                    )
                    expired_sessions = _run_session_maintenance(
                        scoped_factory, maintenance_batch_size,
                    )
                    retention = _run_retention_maintenance(
                        scoped_factory, maintenance_batch_size,
                    )
                    published, retried, dead, requeued = _run_outbox_maintenance(
                        scoped_factory,
                        worker_id=worker_id,
                        batch_size=maintenance_batch_size,
                    )
                    lease_heartbeat.assert_healthy()
                finally:
                    try:
                        lease_heartbeat.stop()
                    finally:
                        try:
                            _release_maintenance_scope(scoped_factory)
                        except Exception:
                            logger.exception(
                                "Could not explicitly release maintenance scope; lease expiry will recover it"
                            )

                totals[0] += promoted
                totals[1] += recovered
                totals[2] += queued
                totals[3] += expired_sessions
                totals[4] += published
                totals[5] += retried
                totals[6] += dead + requeued
                totals[7] += retention["agent_sessions_scrubbed"]
                totals[8] += retention["tool_payloads_purged"]
                cursor_workspace_id = capability.workspace_id
                did_work = did_work or any((
                    promoted, recovered, queued, expired_sessions,
                    published, retried, dead, requeued,
                    retention["agent_sessions_scrubbed"], retention["tool_payloads_purged"],
                ))

            pruned_browser_sessions = _run_browser_session_retention(
                session_factory, maintenance_batch_size,
            )
            if any(totals) or pruned_browser_sessions:
                logger.info(
                    "Capability-scoped worker maintenance completed: promoted=%s recovered=%s "
                    "delegated_queued=%s sessions_expired=%s outbox_published=%s "
                    "outbox_retried=%s outbox_reconciled=%s agent_session_metadata_scrubbed=%s "
                    "tool_payloads_purged=%s browser_sessions_pruned=%s",
                    *totals, pruned_browser_sessions,
                )
            next_maintenance_at = clock() + maintenance_interval_seconds

        if stop_event.is_set():
            break

        execution_id = processor(
            worker_id=worker_id,
            lease_seconds=lease_seconds,
            session_factory=session_factory,
        )
        if execution_id is not None:
            did_work = True

        if not did_work and not stop_event.is_set():
            stop_event.wait(poll_interval_seconds)

    logger.info("Worker stopping: worker_id=%s", worker_id)
