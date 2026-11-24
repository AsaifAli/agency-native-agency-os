
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.audit import record_event
from app.models import (
    Execution,
    ExecutionAttempt,
    ExecutionAttemptStatus,
    ExecutionStatus,
)


MAX_ERROR_MESSAGE_LENGTH = 1000


def _sanitize_error_message(value: str) -> str:
    """Bound persisted worker errors and redact common credential patterns."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError("error_message must be a non-empty string")

    sanitized = re.sub(
        r"(?i)\bBearer\s+[^\s,;]+",
        "Bearer [REDACTED]",
        value,
    )
    sanitized = re.sub(
        r"(?i)\b(authorization|api[_-]?key|access[_-]?token|"
        r"refresh[_-]?token|password|secret)\b\s*[:=]\s*[^\s,;]+",
        r"\1=[REDACTED]",
        sanitized,
    )
    sanitized = re.sub(r"[\x00-\x1f\x7f]", " ", sanitized)
    return sanitized[:MAX_ERROR_MESSAGE_LENGTH]


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


class ExecutionNotFound(WorkerServiceError):
    pass


class AttemptNotFound(WorkerServiceError):
    pass


class WorkerOwnershipError(WorkerServiceError):
    pass


class InvalidExecutionState(WorkerServiceError):
    pass


class LeaseExpired(WorkerServiceError):
    pass


def _validate_lease_seconds(lease_seconds: int) -> None:
    if not 15 <= lease_seconds <= 3600:
        raise ValueError("lease_seconds must be between 15 and 3600")


def _as_utc(value: datetime) -> datetime:
    """Normalize database datetimes, including SQLite naive values."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _get_owned_execution_attempt(
    db: Session,
    *,
    execution_id: str,
    attempt_id: str,
    worker_id: str,
) -> tuple[Execution, ExecutionAttempt]:
    if not worker_id or len(worker_id) > 160:
        raise ValueError("worker_id must contain 1-160 characters")

    execution = (
        db.query(Execution)
        .filter(Execution.id == execution_id)
        .with_for_update()
        .one_or_none()
    )

    if execution is None:
        raise ExecutionNotFound("Execution not found")

    attempt = (
        db.query(ExecutionAttempt)
        .filter(
            ExecutionAttempt.id == attempt_id,
            ExecutionAttempt.execution_id == execution_id,
        )
        .with_for_update()
        .one_or_none()
    )

    if attempt is None:
        raise AttemptNotFound("Attempt not found for this execution")

    if attempt.worker_id != worker_id:
        raise WorkerOwnershipError("Attempt belongs to another worker")

    if attempt.lease_expires_at is None:
        raise InvalidExecutionState("Attempt has no active lease")

    if _as_utc(attempt.lease_expires_at) <= datetime.now(timezone.utc):
        raise LeaseExpired("Worker lease has expired")

    return execution, attempt


def start_execution(
    db: Session,
    *,
    execution_id: str,
    attempt_id: str,
    worker_id: str,
    lease_seconds: int = 60,
) -> tuple[Execution, ExecutionAttempt]:
    """Transition a valid claimed execution and attempt to running."""
    _validate_lease_seconds(lease_seconds)

    execution, attempt = _get_owned_execution_attempt(
        db,
        execution_id=execution_id,
        attempt_id=attempt_id,
        worker_id=worker_id,
    )

    if execution.status != ExecutionStatus.claimed:
        raise InvalidExecutionState("Execution is not claimed")

    if attempt.status != ExecutionAttemptStatus.claimed:
        raise InvalidExecutionState("Attempt is not claimed")

    now = datetime.now(timezone.utc)

    execution.status = ExecutionStatus.running

    if execution.started_at is None:
        execution.started_at = now

    execution.last_attempt_at = now

    attempt.status = ExecutionAttemptStatus.running
    attempt.started_at = now
    attempt.heartbeat_at = now
    attempt.lease_expires_at = now + timedelta(seconds=lease_seconds)

    record_event(
        db,
        execution.org_id,
        None,
        "execution.started",
        "execution",
        execution.id,
        execution.workspace_id,
        {
            "attempt_id": attempt.id,
            "attempt_number": attempt.attempt_number,
            "worker_id": worker_id,
        },
    )

    return execution, attempt


def attach_external_run_id(
    db: Session,
    *,
    execution_id: str,
    attempt_id: str,
    worker_id: str,
    external_run_id: str,
) -> tuple[Execution, ExecutionAttempt]:
    """Persist a provider session ID while the current worker owns its lease.

    This lets a recovered attempt resume the same provider session instead of
    creating a second one after a worker restart or retry.
    """
    if not isinstance(external_run_id, str) or not external_run_id.strip():
        raise ValueError("external_run_id must be a non-empty string")
    if len(external_run_id) > 200:
        raise ValueError("external_run_id must be 200 characters or fewer")

    execution, attempt = _get_owned_execution_attempt(
        db,
        execution_id=execution_id,
        attempt_id=attempt_id,
        worker_id=worker_id,
    )
    if execution.status != ExecutionStatus.running:
        raise InvalidExecutionState("Execution is not running")
    if attempt.status != ExecutionAttemptStatus.running:
        raise InvalidExecutionState("Attempt is not running")
    if attempt.external_run_id and attempt.external_run_id != external_run_id:
        raise InvalidExecutionState("Attempt is already linked to another provider run")

    attempt.external_run_id = external_run_id
    record_event(
        db,
        execution.org_id,
        None,
        "execution.external_run_linked",
        "execution",
        execution.id,
        execution.workspace_id,
        {
            "attempt_id": attempt.id,
            "provider": attempt.runtime,
            "external_run_id": external_run_id,
        },
    )
    db.flush()
    return execution, attempt


def heartbeat_execution(
    db: Session,
    *,
    execution_id: str,
    attempt_id: str,
    worker_id: str,
    lease_seconds: int = 60,
) -> tuple[Execution, ExecutionAttempt]:
    """Renew the lease of an active claimed or running attempt."""
    _validate_lease_seconds(lease_seconds)

    execution, attempt = _get_owned_execution_attempt(
        db,
        execution_id=execution_id,
        attempt_id=attempt_id,
        worker_id=worker_id,
    )

    if execution.status not in (
        ExecutionStatus.claimed,
        ExecutionStatus.running,
    ):
        raise InvalidExecutionState("Execution is not active")

    if attempt.status not in (
        ExecutionAttemptStatus.claimed,
        ExecutionAttemptStatus.running,
    ):
        raise InvalidExecutionState("Attempt is not active")

    now = datetime.now(timezone.utc)

    attempt.heartbeat_at = now
    attempt.lease_expires_at = now + timedelta(seconds=lease_seconds)

    return execution, attempt


def complete_execution(
    db: Session,
    *,
    execution_id: str,
    attempt_id: str,
    worker_id: str,
    result: dict,
) -> tuple[Execution, ExecutionAttempt]:
    """Persist a successful result and complete the execution."""
    if not isinstance(result, dict):
        raise ValueError("result must be a dictionary")

    execution, attempt = _get_owned_execution_attempt(
        db,
        execution_id=execution_id,
        attempt_id=attempt_id,
        worker_id=worker_id,
    )

    if execution.status != ExecutionStatus.running:
        raise InvalidExecutionState("Execution is not running")

    if attempt.status != ExecutionAttemptStatus.running:
        raise InvalidExecutionState("Attempt is not running")

    now = datetime.now(timezone.utc)

    execution.status = ExecutionStatus.succeeded
    execution.result = result
    execution.finished_at = now
    execution.error_code = None
    execution.error_message = None

    attempt.status = ExecutionAttemptStatus.succeeded
    attempt.result = result
    attempt.finished_at = now
    attempt.lease_expires_at = None
    attempt.heartbeat_at = now
    attempt.error_code = None
    attempt.error_message = None

    record_event(
        db,
        execution.org_id,
        None,
        "execution.succeeded",
        "execution",
        execution.id,
        execution.workspace_id,
        {
            "attempt_id": attempt.id,
            "attempt_number": attempt.attempt_number,
            "worker_id": worker_id,
        },
    )

    return execution, attempt


def fail_execution(
    db: Session,
    *,
    execution_id: str,
    attempt_id: str,
    worker_id: str,
    error_code: str,
    error_message: str,
    retryable: bool = True,
    base_delay_seconds: int = 30,
    max_delay_seconds: int = 3600,
) -> tuple[Execution, ExecutionAttempt]:
    """
    Record a failed attempt and either schedule a retry or fail permanently.

    The caller owns the transaction and must commit or roll back.
    Error messages are sanitized and bounded again at this persistence
    boundary; callers should still avoid passing raw provider exceptions.
    """
    if (
        not isinstance(base_delay_seconds, int)
        or isinstance(base_delay_seconds, bool)
        or not isinstance(max_delay_seconds, int)
        or isinstance(max_delay_seconds, bool)
    ):
        raise ValueError("Retry delays must be integers")

    if not isinstance(retryable, bool):
        raise ValueError("retryable must be a boolean")
    if (
        not isinstance(error_code, str)
        or not error_code.strip()
        or len(error_code) > 100
    ):
        raise ValueError("error_code must contain 1-100 characters")

    error_message = _sanitize_error_message(error_message)

    if base_delay_seconds < 1:
        raise ValueError("base_delay_seconds must be at least 1")

    if max_delay_seconds < base_delay_seconds:
        raise ValueError(
            "max_delay_seconds must be greater than or equal to base_delay_seconds"
        )

    execution, attempt = _get_owned_execution_attempt(
        db,
        execution_id=execution_id,
        attempt_id=attempt_id,
        worker_id=worker_id,
    )

    if execution.status != ExecutionStatus.running:
        raise InvalidExecutionState("Execution is not running")

    if attempt.status != ExecutionAttemptStatus.running:
        raise InvalidExecutionState("Attempt is not running")

    now = datetime.now(timezone.utc)

    execution.error_code = error_code
    execution.error_message = error_message

    attempt.status = ExecutionAttemptStatus.failed
    attempt.finished_at = now
    attempt.lease_expires_at = None
    attempt.heartbeat_at = now
    attempt.error_code = error_code
    attempt.error_message = error_message

    retry_scheduled = (
        retryable and execution.attempt_count < execution.max_attempts
    )

    if retry_scheduled:
        delay_seconds = min(
            base_delay_seconds * (2 ** (attempt.attempt_number - 1)),
            max_delay_seconds,
        )

        execution.status = ExecutionStatus.retry_wait
        execution.next_retry_at = now + timedelta(seconds=delay_seconds)
        execution.finished_at = None

        record_event(
            db,
            execution.org_id,
            None,
            "execution.retry_scheduled",
            "execution",
            execution.id,
            execution.workspace_id,
            {
                "attempt_id": attempt.id,
                "attempt_number": attempt.attempt_number,
                "worker_id": worker_id,
                "error_code": error_code,
                "retry_delay_seconds": delay_seconds,
                "next_retry_at": execution.next_retry_at.isoformat(),
            },
        )
    else:
        execution.status = ExecutionStatus.failed
        execution.next_retry_at = None
        execution.finished_at = now

        record_event(
            db,
            execution.org_id,
            None,
            "execution.failed",
            "execution",
            execution.id,
            execution.workspace_id,
            {
                "attempt_id": attempt.id,
                "attempt_number": attempt.attempt_number,
                "worker_id": worker_id,
                "error_code": error_code,
                "retryable": retryable,
                "attempts_exhausted": (
                    execution.attempt_count >= execution.max_attempts
                ),
            },
        )

    record_event(
        db,
        execution.org_id,
        None,
        "execution.attempt_failed",
        "execution_attempt",
        attempt.id,
        execution.workspace_id,
        {
            "execution_id": execution.id,
            "attempt_number": attempt.attempt_number,
            "worker_id": worker_id,
            "error_code": error_code,
        },
    )

    return execution, attempt

def promote_due_retries(
    db: Session,
    *,
    limit: int = 100,
) -> int:
    """
    Move due retry_wait executions back to queued.

    Workers still claim executions through claim_next_execution().
    The caller owns the transaction and must commit or roll back.
    """
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")

    now = datetime.now(timezone.utc)

    executions = (
        db.query(Execution)
        .filter(
            Execution.status == ExecutionStatus.retry_wait,
            Execution.next_retry_at.is_not(None),
            Execution.next_retry_at <= now,
        )
        .order_by(
            Execution.next_retry_at.asc(),
            Execution.created_at.asc(),
            Execution.id.asc(),
        )
        .with_for_update(skip_locked=True)
        .limit(limit)
        .all()
    )

    for execution in executions:
        execution.status = ExecutionStatus.queued
        execution.next_retry_at = None
        execution.queued_at = now

        record_event(
            db,
            execution.org_id,
            None,
            "execution.retry_queued",
            "execution",
            execution.id,
            execution.workspace_id,
            {
                "attempt_count": execution.attempt_count,
            },
        )

    if executions:
        db.flush()

    return len(executions)

def recover_expired_execution_leases(
    db: Session,
    *,
    limit: int = 100,
    base_delay_seconds: int = 30,
    max_delay_seconds: int = 3600,
) -> int:
    """
    Recover executions whose active worker attempt has an expired lease.

    Expired attempts become abandoned. Executions are either scheduled
    for retry or marked failed when attempts are exhausted.

    The caller owns the transaction and must commit or roll back.
    """
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise ValueError("limit must be an integer")

    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")

    if (
        not isinstance(base_delay_seconds, int)
        or isinstance(base_delay_seconds, bool)
        or not isinstance(max_delay_seconds, int)
        or isinstance(max_delay_seconds, bool)
    ):
        raise ValueError("Retry delays must be integers")

    if base_delay_seconds < 1:
        raise ValueError("base_delay_seconds must be at least 1")

    if max_delay_seconds < base_delay_seconds:
        raise ValueError(
            "max_delay_seconds must be greater than or equal to "
            "base_delay_seconds"
        )

    now = datetime.now(timezone.utc)

    # Discover candidate execution IDs without locking attempts first.
    # We subsequently lock each execution before its attempt, preserving
    # the lock order used by the normal worker lifecycle.
    candidate_ids = (
        db.query(Execution.id)
        .join(
            ExecutionAttempt,
            ExecutionAttempt.execution_id == Execution.id,
        )
        .filter(
            Execution.status.in_(
                (ExecutionStatus.claimed, ExecutionStatus.running)
            ),
            ExecutionAttempt.status.in_(
                (
                    ExecutionAttemptStatus.claimed,
                    ExecutionAttemptStatus.running,
                )
            ),
            ExecutionAttempt.lease_expires_at.is_not(None),
            ExecutionAttempt.lease_expires_at <= now,
        )
        .distinct()
        .order_by(Execution.id.asc())
        .limit(limit)
        .all()
    )

    recovered_count = 0

    for (execution_id,) in candidate_ids:
        # Lock execution first. PostgreSQL skips executions already
        # being processed by another recovery or worker operation.
        execution = (
            db.query(Execution)
            .filter(Execution.id == execution_id)
            .with_for_update(skip_locked=True)
            .one_or_none()
        )

        if execution is None:
            continue

        if execution.status not in (
            ExecutionStatus.claimed,
            ExecutionStatus.running,
        ):
            continue

        # Lock and re-check the expired attempt after acquiring the
        # execution lock. Another transaction may have renewed its lease.
        attempt = (
            db.query(ExecutionAttempt)
            .filter(
                ExecutionAttempt.execution_id == execution.id,
                ExecutionAttempt.status.in_(
                    (
                        ExecutionAttemptStatus.claimed,
                        ExecutionAttemptStatus.running,
                    )
                ),
                ExecutionAttempt.lease_expires_at.is_not(None),
                ExecutionAttempt.lease_expires_at <= now,
            )
            .order_by(
                ExecutionAttempt.lease_expires_at.asc(),
                ExecutionAttempt.id.asc(),
            )
            .with_for_update()
            .first()
        )

        if attempt is None:
            continue

        error_code = "WORKER_LEASE_EXPIRED"
        error_message = "Worker lease expired before attempt completion."

        attempt.status = ExecutionAttemptStatus.abandoned
        attempt.finished_at = now
        attempt.lease_expires_at = None
        attempt.error_code = error_code
        attempt.error_message = error_message

        execution.error_code = error_code
        execution.error_message = error_message

        retry_scheduled = execution.attempt_count < execution.max_attempts

        record_event(
            db,
            execution.org_id,
            None,
            "execution.attempt_abandoned",
            "execution_attempt",
            attempt.id,
            execution.workspace_id,
            {
                "execution_id": execution.id,
                "attempt_number": attempt.attempt_number,
                "worker_id": attempt.worker_id,
                "error_code": error_code,
            },
        )

        if retry_scheduled:
            delay_seconds = min(
                base_delay_seconds * (2 ** (attempt.attempt_number - 1)),
                max_delay_seconds,
            )

            execution.status = ExecutionStatus.retry_wait
            execution.next_retry_at = now + timedelta(
                seconds=delay_seconds
            )
            execution.finished_at = None

            record_event(
                db,
                execution.org_id,
                None,
                "execution.retry_scheduled",
                "execution",
                execution.id,
                execution.workspace_id,
                {
                    "attempt_id": attempt.id,
                    "attempt_number": attempt.attempt_number,
                    "worker_id": attempt.worker_id,
                    "error_code": error_code,
                    "retry_delay_seconds": delay_seconds,
                    "next_retry_at": execution.next_retry_at.isoformat(),
                    "recovery_reason": "expired_worker_lease",
                },
            )
        else:
            execution.status = ExecutionStatus.failed
            execution.next_retry_at = None
            execution.finished_at = now

            record_event(
                db,
                execution.org_id,
                None,
                "execution.failed",
                "execution",
                execution.id,
                execution.workspace_id,
                {
                    "attempt_id": attempt.id,
                    "attempt_number": attempt.attempt_number,
                    "worker_id": attempt.worker_id,
                    "error_code": error_code,
                    "retryable": True,
                    "attempts_exhausted": True,
                    "recovery_reason": "expired_worker_lease",
                },
            )

        recovered_count += 1

    if recovered_count:
        db.flush()

    return recovered_count
