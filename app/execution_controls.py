"""Durable, workspace-scoped execution control requests.

Provider interruption and worker acknowledgement are separate lifecycle steps;
a request is never represented as a completed cancellation until the worker has
observed it or the execution was still safely queued.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.audit import record_event
from app.models import Execution, ExecutionStatus


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

    if execution.status in {ExecutionStatus.queued, ExecutionStatus.retry_wait}:
        execution.status = ExecutionStatus.cancelled
        execution.finished_at = now
        execution.error_code = "EXECUTION_CANCELLED"
        execution.error_message = "Execution cancelled before worker start."
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
