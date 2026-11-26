"""Durable, workspace-scoped execution control requests.

Provider interruption and worker acknowledgement are separate lifecycle steps;
a request is never represented as a completed cancellation until the worker has
observed it or the execution was still safely queued.
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid

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
    control_request = {
        "action": "cancel",
        "requested_at": now.isoformat(),
        "requested_by": actor_user_id,
    }
    if isinstance(existing, dict) and existing.get("interrupt_event_id"):
        control_request["interrupt_event_id"] = existing["interrupt_event_id"]
    metadata["control_request"] = control_request
    execution.request_metadata = metadata
    execution.updated_at = now

    if (execution.status in {ExecutionStatus.queued, ExecutionStatus.retry_wait} and execution.attempt_count == 0) or execution.status == ExecutionStatus.paused:
        was_paused = execution.status == ExecutionStatus.paused
        execution.status = ExecutionStatus.cancelled
        execution.finished_at = now
        execution.error_code = "EXECUTION_CANCELLED"
        execution.error_message = (
            "Execution cancelled from paused state."
            if was_paused
            else "Execution cancelled before worker start."
        )
        _sync_task_delegation(db, execution, "cancelled", "EXECUTION_CANCELLED")
        _sync_plan_draft_execution(db, execution, "cancelled", "EXECUTION_CANCELLED")
        record_event(
            db, org_id, actor_user_id, "execution.cancelled",
            "execution", execution.id, workspace_id,
            {"previous_status": "paused" if was_paused else "queued_or_retry_wait", "control": "cancel"},
        )
    else:
        previous_status = execution.status.value
        if execution.status in {ExecutionStatus.queued, ExecutionStatus.retry_wait}:
            if execution.attempt_count >= execution.max_attempts:
                # No worker attempt remains to reconcile an earlier provider call.
                # Do not falsely report a successful cancellation.
                execution.status = ExecutionStatus.failed
                execution.finished_at = now
                execution.error_code = "CANCEL_REQUIRES_MANUAL_REVIEW"
                execution.error_message = (
                    "Cancellation requested after retry exhaustion; provider outcome requires manual reconciliation."
                )
                _sync_task_delegation(
                    db, execution, "failed", "CANCEL_REQUIRES_MANUAL_REVIEW"
                )
                _sync_plan_draft_execution(
                    db, execution, "failed", "CANCEL_REQUIRES_MANUAL_REVIEW"
                )
                record_event(
                    db, org_id, actor_user_id,
                    "execution.cancel_reconciliation_required",
                    "execution", execution.id, workspace_id,
                    {"previous_status": previous_status, "control": "cancel"},
                )
                db.flush()
                return execution
            if execution.status == ExecutionStatus.retry_wait:
                # Bring reconciliation forward rather than waiting for the old
                # retry backoff. The worker will reuse the persisted provider ID.
                execution.status = ExecutionStatus.queued
                execution.next_retry_at = None
                execution.queued_at = now

        record_event(
            db, org_id, actor_user_id, "execution.cancel_requested",
            "execution", execution.id, workspace_id,
            {"previous_status": previous_status, "control": "cancel"},
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
    if isinstance(request, dict) and request.get("action") in {"cancel", "pause"}:
        return request["action"]
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



def request_execution_pause(
    db: Session, *, execution_id: str, org_id: str, workspace_id: str,
    actor_user_id: str,
) -> Execution:
    """Persist a pause request; active work is paused only after provider acknowledgement."""
    if not actor_user_id:
        raise ValueError("actor_user_id is required")
    execution = (
        db.query(Execution)
        .filter_by(id=execution_id, org_id=org_id, workspace_id=workspace_id)
        .with_for_update().one_or_none()
    )
    if execution is None:
        raise ExecutionNotFound("Execution not found")
    if execution.status in {ExecutionStatus.succeeded, ExecutionStatus.failed, ExecutionStatus.cancelled}:
        raise InvalidExecutionState("A terminal execution cannot be paused")
    metadata = dict(execution.request_metadata or {})
    existing = metadata.get("control_request")
    if isinstance(existing, dict) and existing.get("action") == "pause":
        return execution
    if isinstance(existing, dict) and existing.get("action") == "cancel":
        raise InvalidExecutionState("Cancellation is already requested and cannot be downgraded to pause")
    if execution.status == ExecutionStatus.paused:
        return execution
    if execution.runtime != "claude_managed_agents" and not (
        execution.status == ExecutionStatus.queued and execution.attempt_count == 0
    ):
        raise InvalidExecutionState(
            "This runtime cannot safely pause an active or previously attempted execution."
        )

    now = datetime.now(timezone.utc)
    previous_status = execution.status.value
    metadata["control_request"] = {
        "action": "pause", "requested_at": now.isoformat(),
        "requested_by": actor_user_id,
    }
    execution.request_metadata = metadata
    execution.updated_at = now

    if execution.status == ExecutionStatus.queued and execution.attempt_count == 0:
        execution.status = ExecutionStatus.paused
        _sync_task_delegation(db, execution, "paused")
        _sync_plan_draft_execution(db, execution, "paused")
        record_event(db, org_id, actor_user_id, "execution.paused",
                     "execution", execution.id, workspace_id,
                     {"previous_status": previous_status, "control": "pause",
                      "provider_interruption_acknowledged": False,
                      "reason": "not_started"})
    else:
        if execution.status in {ExecutionStatus.queued, ExecutionStatus.retry_wait}:
            if execution.attempt_count >= execution.max_attempts:
                execution.status = ExecutionStatus.failed
                execution.finished_at = now
                execution.error_code = "PAUSE_REQUIRES_MANUAL_REVIEW"
                execution.error_message = "Pause requested after retry exhaustion; provider state requires manual reconciliation."
                _sync_task_delegation(db, execution, "failed", execution.error_code)
                _sync_plan_draft_execution(db, execution, "failed", execution.error_code)
                record_event(db, org_id, actor_user_id, "execution.pause_reconciliation_required",
                             "execution", execution.id, workspace_id,
                             {"previous_status": previous_status, "control": "pause"})
                db.flush()
                return execution
            execution.status = ExecutionStatus.queued
            execution.next_retry_at = None
            execution.queued_at = now
        record_event(db, org_id, actor_user_id, "execution.pause_requested",
                     "execution", execution.id, workspace_id,
                     {"previous_status": previous_status, "control": "pause"})
    db.flush()
    return execution


def acknowledge_execution_pause(
    db: Session, *, execution_id: str, attempt_id: str, worker_id: str,
) -> tuple[Execution, object]:
    """Acknowledge pause only after the provider adapter confirms idle/drained state."""
    execution, attempt = _get_owned_execution_attempt(
        db, execution_id=execution_id, attempt_id=attempt_id, worker_id=worker_id,
    )
    request = (execution.request_metadata or {}).get("control_request")
    if not isinstance(request, dict) or request.get("action") != "pause":
        raise InvalidExecutionState("No durable pause request exists")
    if execution.status not in {ExecutionStatus.claimed, ExecutionStatus.running}:
        raise InvalidExecutionState("Execution is not in an active pausable state")
    if attempt.status not in {ExecutionAttemptStatus.claimed, ExecutionAttemptStatus.running}:
        raise InvalidExecutionState("Attempt is not active")
    now = datetime.now(timezone.utc)
    execution.status = ExecutionStatus.paused
    execution.finished_at = None
    execution.error_code = None
    execution.error_message = None
    attempt.status = ExecutionAttemptStatus.paused
    attempt.finished_at = now
    attempt.lease_expires_at = None
    attempt.heartbeat_at = now
    attempt.error_code = None
    attempt.error_message = None
    _sync_task_delegation(db, execution, "paused")
    _sync_plan_draft_execution(db, execution, "paused")
    record_event(
        db, execution.org_id, request.get("requested_by"), "execution.paused",
        "execution", execution.id, execution.workspace_id,
        {"attempt_id": attempt.id, "attempt_number": attempt.attempt_number,
         "worker_id": worker_id, "provider_interruption_acknowledged": True},
    )
    db.flush()
    return execution, attempt


def resume_execution(
    db: Session, *, execution_id: str, org_id: str, workspace_id: str,
    actor_user_id: str,
) -> Execution:
    """Queue a paused execution to continue its existing provider session."""
    if not actor_user_id:
        raise ValueError("actor_user_id is required")
    execution = (
        db.query(Execution)
        .filter_by(id=execution_id, org_id=org_id, workspace_id=workspace_id)
        .with_for_update().one_or_none()
    )
    if execution is None:
        raise ExecutionNotFound("Execution not found")
    existing_control = (execution.request_metadata or {}).get("control_request")
    if (
        isinstance(existing_control, dict)
        and existing_control.get("action") == "resume"
        and execution.status in {ExecutionStatus.queued, ExecutionStatus.claimed, ExecutionStatus.running}
    ):
        return execution
    if execution.status != ExecutionStatus.paused:
        raise InvalidExecutionState("Only a paused execution can be resumed")
    if execution.attempt_count >= execution.max_attempts:
        raise InvalidExecutionState("Execution retry budget is exhausted; manual review is required")
    now = datetime.now(timezone.utc)
    metadata = dict(execution.request_metadata or {})
    metadata["control_request"] = {
        "action": "resume", "requested_at": now.isoformat(),
        "requested_by": actor_user_id, "resume_token": uuid.uuid4().hex,
        "resume_event_id": None,
    }
    execution.request_metadata = metadata
    execution.status = ExecutionStatus.queued
    execution.next_retry_at = None
    execution.queued_at = now
    execution.finished_at = None
    execution.error_code = None
    execution.error_message = None
    execution.updated_at = now
    _sync_task_delegation(db, execution, "queued")
    _sync_plan_draft_execution(db, execution, "queued")
    record_event(
        db, org_id, actor_user_id, "execution.resume_requested",
        "execution", execution.id, workspace_id,
        {"resume_token": metadata["control_request"]["resume_token"],
         "provider_session_reuse_required": True},
    )
    db.flush()
    return execution


def persist_execution_resume_event(
    db: Session, *, execution_id: str, attempt_id: str, worker_id: str,
    resume_token: str, provider_event_id: str,
) -> None:
    """Persist the provider resume event under the current worker lease."""
    if not isinstance(provider_event_id, str) or not provider_event_id.strip():
        raise ValueError("provider_event_id is required")
    execution, _attempt = _get_owned_execution_attempt(
        db, execution_id=execution_id, attempt_id=attempt_id, worker_id=worker_id,
    )
    metadata = dict(execution.request_metadata or {})
    request = dict(metadata.get("control_request") or {})
    if request.get("action") != "resume" or request.get("resume_token") != resume_token:
        raise InvalidExecutionState("Resume token no longer matches the active request")
    existing = request.get("resume_event_id")
    if existing and existing != provider_event_id:
        raise InvalidExecutionState("A different provider resume event is already persisted")
    request["resume_event_id"] = provider_event_id
    metadata["control_request"] = request
    execution.request_metadata = metadata
    db.flush()



def persist_execution_control_event(
    db: Session, *, execution_id: str, attempt_id: str, worker_id: str,
    action: str, provider_event_id: str,
) -> None:
    """Persist the provider interrupt ID while the worker still owns its lease."""
    if action not in {"pause", "cancel"}:
        raise ValueError("action must be pause or cancel")
    if not isinstance(provider_event_id, str) or not provider_event_id.strip():
        raise ValueError("provider_event_id is required")
    execution, _attempt = _get_owned_execution_attempt(
        db, execution_id=execution_id, attempt_id=attempt_id, worker_id=worker_id,
    )
    metadata = dict(execution.request_metadata or {})
    request = dict(metadata.get("control_request") or {})
    if request.get("action") not in {"pause", "cancel"}:
        raise InvalidExecutionState("No active provider interruption request exists")
    existing = request.get("interrupt_event_id")
    if existing and existing != provider_event_id:
        raise InvalidExecutionState("A different provider interrupt event is already persisted")
    request["interrupt_event_id"] = provider_event_id
    request["interrupt_action"] = action
    metadata["control_request"] = request
    execution.request_metadata = metadata
    db.flush()
