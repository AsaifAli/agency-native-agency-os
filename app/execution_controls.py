"""Durable, workspace-scoped execution control requests.

Provider interruption and worker acknowledgement are separate lifecycle steps;
a request is never represented as a completed cancellation until the worker has
observed it or the execution was still safely queued.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.audit import record_event
from app.models import Execution, ExecutionAttemptStatus, ExecutionStatus
from app.worker_service import (
    _get_owned_execution_attempt,
    _sync_plan_draft_execution,
    _sync_task_delegation,
)


class ExecutionControlError(Exception):
    """Base exception for execution-control lifecycle errors."""


class ExecutionNotFound(ExecutionControlError):
    """Execution is not visible in the requested organization/workspace."""


class InvalidExecutionState(ExecutionControlError):
    """The requested control is not valid for the execution's current state."""


def request_execution_cancel(
    db: Session,
    *,
    execution_id: str,
    org_id: str,
    workspace_id: str,
    actor_user_id: str,
) -> Execution:
    """Request cancellation under a locked, exact workspace-scoped execution.

    Queued/retry-wait work is cancelled immediately because no worker owns it.
    Claimed/running work receives a durable cooperative request; the worker must
    acknowledge it before the execution becomes terminal.
    """
    if not actor_user_id:
        raise ValueError("actor_user_id is required")

    execution = (
        db.query(Execution)
        .filter_by(
            id=execution_id,
            org_id=org_id,
            workspace_id=workspace_id,
        )
        .with_for_update()
        .one_or_none()
    )
    if execution is None:
        raise ExecutionNotFound("Execution not found")

    if execution.status in {
        ExecutionStatus.succeeded,
        ExecutionStatus.failed,
        ExecutionStatus.cancelled,
    }:
        raise InvalidExecutionState("A terminal execution cannot be cancelled")

    metadata = dict(execution.request_metadata or {})
    existing = metadata.get("control_request")
    if isinstance(existing, dict) and existing.get("action") == "cancel":
        return execution

    now = datetime.now(timezone.utc)
    metadata["control_request"] = {
        "action": "cancel",
        "requested_at": now.isoformat(),
        "requested_by": actor_user_id,
    }
    execution.request_metadata = metadata
    execution.updated_at = now

    if execution.status in {ExecutionStatus.queued, ExecutionStatus.retry_wait} and execution.attempt_count == 0:
        execution.status = ExecutionStatus.cancelled
        execution.finished_at = now
        execution.error_code = "EXECUTION_CANCELLED"
        execution.error_message = "Execution cancelled before worker start."
        _sync_task_delegation(db, execution, "cancelled", "EXECUTION_CANCELLED")
        _sync_plan_draft_execution(db, execution, "cancelled", "EXECUTION_CANCELLED")
        record_event(
            db, org_id, actor_user_id, "execution.cancelled",
            "execution", execution.id, workspace_id,
            {"previous_status": "queued_or_retry_wait", "control": "cancel"},
        )
    else:
        record_event(
            db, org_id, actor_user_id, "execution.cancel_requested",
            "execution", execution.id, workspace_id,
            {"previous_status": execution.status.value, "control": "cancel"},
        )

    db.flush()
    return execution


def get_execution_control_request(
    db: Session,
    *,
    execution_id: str,
    attempt_id: str,
    worker_id: str,
) -> str | None:
    """Read a control request only while the supplied worker owns the live lease."""
    execution, _attempt = _get_owned_execution_attempt(
        db,
        execution_id=execution_id,
        attempt_id=attempt_id,
        worker_id=worker_id,
    )
    request = (execution.request_metadata or {}).get("control_request")
    if isinstance(request, dict) and request.get("action") == "cancel":
        return "cancel"
    return None


def acknowledge_execution_cancel(
    db: Session,
    *,
    execution_id: str,
    attempt_id: str,
    worker_id: str,
) -> tuple[Execution, object]:
    """Atomically acknowledge cancellation after provider interruption/drain."""
    execution, attempt = _get_owned_execution_attempt(
        db,
        execution_id=execution_id,
        attempt_id=attempt_id,
        worker_id=worker_id,
    )
    request = (execution.request_metadata or {}).get("control_request")
    if not isinstance(request, dict) or request.get("action") != "cancel":
        raise InvalidExecutionState("No durable cancellation request exists")
    if execution.status not in {ExecutionStatus.claimed, ExecutionStatus.running}:
        raise InvalidExecutionState("Execution is not in a cancellable active state")
    if attempt.status not in {ExecutionAttemptStatus.claimed, ExecutionAttemptStatus.running}:
        raise InvalidExecutionState("Attempt is not active")

    now = datetime.now(timezone.utc)
    execution.status = ExecutionStatus.cancelled
    execution.finished_at = now
    execution.error_code = "EXECUTION_CANCELLED"
    execution.error_message = "Execution cancelled after worker acknowledgement."
    attempt.status = ExecutionAttemptStatus.failed
    attempt.finished_at = now
    attempt.lease_expires_at = None
    attempt.heartbeat_at = now
    attempt.error_code = "EXECUTION_CANCELLED"
    attempt.error_message = "Provider interruption acknowledged by worker."

    _sync_task_delegation(db, execution, "cancelled", "EXECUTION_CANCELLED")
    _sync_plan_draft_execution(db, execution, "cancelled", "EXECUTION_CANCELLED")
    record_event(
        db,
        execution.org_id,
        request.get("requested_by"),
        "execution.cancelled",
        "execution",
        execution.id,
        execution.workspace_id,
        {
            "attempt_id": attempt.id,
            "attempt_number": attempt.attempt_number,
            "worker_id": worker_id,
            "provider_interruption_acknowledged": True,
        },
    )
    db.flush()
    return execution, attempt
