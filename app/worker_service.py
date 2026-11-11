
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.audit import record_event
from app.models import (
    Execution,
    ExecutionAttempt,
    ExecutionAttemptStatus,
    ExecutionStatus,
)


class WorkerServiceError(Exception):
    """Base exception for worker lifecycle errors."""


def claim_next_execution(
    db: Session,
    *,
    worker_id: str,
    lease_seconds: int = 60,
) -> tuple[Execution, ExecutionAttempt] | None:
    """
    Atomically claim the oldest eligible queued execution.

    PostgreSQL uses FOR UPDATE SKIP LOCKED to prevent multiple
    workers from claiming the same execution.

    The caller owns the transaction and must commit or roll back.
    No runtime or external provider is invoked here.
    """

    if not worker_id or len(worker_id) > 160:
        raise ValueError("worker_id must contain 1-160 characters")

    if not 15 <= lease_seconds <= 3600:
        raise ValueError("lease_seconds must be between 15 and 3600")

    now = datetime.now(timezone.utc)

    execution = (
        db.query(Execution)
        .filter(
            Execution.status == ExecutionStatus.queued,
            Execution.attempt_count < Execution.max_attempts,
        )
        .order_by(
            Execution.queued_at.asc(),
            Execution.created_at.asc(),
            Execution.id.asc(),
        )
        .with_for_update(skip_locked=True)
        .first()
    )

    if execution is None:
        return None

    next_attempt_number = execution.attempt_count + 1

    execution.status = ExecutionStatus.claimed
    execution.attempt_count = next_attempt_number

    attempt = ExecutionAttempt(
        execution_id=execution.id,
        attempt_number=next_attempt_number,
        worker_id=worker_id,
        runtime=execution.runtime,
        status=ExecutionAttemptStatus.claimed,
        lease_expires_at=now + timedelta(seconds=lease_seconds),
        heartbeat_at=now,
    )

    db.add(attempt)
    db.flush()

    record_event(
        db,
        execution.org_id,
        None,
        "execution.claimed",
        "execution",
        execution.id,
        execution.workspace_id,
        {
            "attempt_id": attempt.id,
            "attempt_number": next_attempt_number,
            "worker_id": worker_id,
            "lease_seconds": lease_seconds,
        },
    )

    return execution, attempt
