
import re
import hashlib
import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit import record_event
from app.models import (
    AuditEvent,
    Execution,
    ExecutionAttempt,
    ExecutionAttemptStatus,
    ExecutionStatus,
    Task,
)
from app.workforce_models import Delegation, WorkforceMember, OrchestrationPlanDraft


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



def _validate_provider_usage(value: dict | None) -> dict | None:
    """Accept only the normalized numeric usage contract emitted by the runtime adapter."""
    if value is None:
        return None
    allowed = {
        "input_tokens", "output_tokens", "cache_read_input_tokens",
        "cache_creation_input_tokens", "list_cost_minor", "currency",
        "active_seconds", "server_tool_use",
    }
    if not isinstance(value, dict) or set(value) - allowed:
        raise ValueError("provider_usage must match the normalized usage contract")
    for key in ("input_tokens", "output_tokens", "cache_read_input_tokens",
                "cache_creation_input_tokens", "list_cost_minor"):
        item = value.get(key)
        if item is not None and (isinstance(item, bool) or not isinstance(item, int) or not 0 <= item <= 10**12):
            raise ValueError("provider_usage contains an invalid counter")
    if ("list_cost_minor" in value) != (value.get("currency") == "USD"):
        raise ValueError("provider_usage list cost must be denominated in USD")
    if "currency" in value and value["currency"] != "USD":
        raise ValueError("provider_usage currency is unsupported")
    active = value.get("active_seconds")
    if active is not None and (isinstance(active, bool) or not isinstance(active, (int, float)) or not 0 <= active <= 31_536_000):
        raise ValueError("provider_usage contains invalid active time")
    tools = value.get("server_tool_use")
    if tools is not None and (
        not isinstance(tools, dict) or set(tools) - {"web_search_requests", "web_fetch_requests"}
        or any(isinstance(item, bool) or not isinstance(item, int) or not 0 <= item <= 10**9 for item in tools.values())
    ):
        raise ValueError("provider_usage contains invalid server-tool counts")
    return dict(value)


def _sync_plan_draft_execution(
    db: Session,
    execution: Execution,
    state: str,
    error_code: str | None = None,
) -> None:
    """Keep a durable Chief of Staff draft in step with its OS execution."""
    draft = db.query(OrchestrationPlanDraft).filter_by(
        id=(execution.request_metadata or {}).get("plan_draft_id"),
        org_id=execution.org_id,
        workspace_id=execution.workspace_id,
        execution_id=execution.id,
    ).with_for_update().one_or_none()
    if draft is None:
        return

    task = db.query(Task).filter_by(
        id=draft.task_id, org_id=draft.org_id,
        workspace_id=draft.workspace_id,
    ).with_for_update().one_or_none()

    if state == "succeeded":
        from app.workforce_planning import PlanDraftOutputError, validate_plan_draft_output
        try:
            detail = (execution.result or {}).get("detail", "")
            draft.suggested_plan = validate_plan_draft_output(detail)
        except PlanDraftOutputError:
            draft.status = "invalid_output"
            draft.error_code = "PLAN_DRAFT_OUTPUT_INVALID"
            if task:
                task.status = "failed"
        else:
            draft.status = "ready_for_review"
            draft.error_code = None
            if task:
                task.status = "awaiting_review"
    elif state == "paused":
        draft.status = "paused"
        draft.error_code = None
        if task:
            task.status = "paused"
    elif state == "running":
        draft.status = "running"
        draft.error_code = None
        if task:
            task.status = "running"
    elif state == "queued":
        draft.status = "queued"
        draft.error_code = error_code
        if task:
            task.status = "queued"
    elif state == "failed":
        draft.status = "failed"
        draft.error_code = error_code or "PLAN_DRAFT_EXECUTION_FAILED"
        if task:
            task.status = "failed"
    elif state == "cancelled":
        draft.status = "cancelled"
        draft.error_code = error_code
        if task:
            task.status = "cancelled"

    draft.updated_at = datetime.now(timezone.utc)
    record_event(
        db, execution.org_id, None, "workforce.plan_draft_state_changed",
        "orchestration_plan_draft", draft.id, execution.workspace_id,
        {"status": draft.status, "execution_id": execution.id,
         "error_code": draft.error_code},
    )


def _sync_task_delegation(db: Session, execution: Execution, state: str,
                          error_code: str | None = None) -> None:
    """Synchronize a delegated task's business status with its execution."""
    task = db.query(Task).filter_by(
        id=execution.task_id, org_id=execution.org_id,
        workspace_id=execution.workspace_id,
    ).first()
    if task is None:
        return
    task.status = state
    row = db.query(Delegation).filter_by(
        org_id=execution.org_id, workspace_id=execution.workspace_id,
        child_task_id=task.id,
    ).with_for_update().first()
    if row is None:
        return
    row.status = "awaiting_review" if state == "succeeded" and row.review_required else state
    if state == "succeeded" and not row.review_required and row.review_status == "pending":
        row.review_status = "waived"
    if error_code:
        row.last_error_code = error_code
    elif state in {"running", "succeeded", "queued", "paused"}:
        row.last_error_code = None
    row.updated_at = datetime.now(timezone.utc)
    record_event(
        db, execution.org_id, None, "workforce.delegated_task_state_changed",
        "delegation", row.id, execution.workspace_id,
        {"task_id": task.id, "status": row.status, "error_code": error_code},
    )


class WorkerServiceError(Exception):
    """Base exception for worker lifecycle errors."""


@dataclass(frozen=True)
class WorkerExecutionCapability:
    """Short-lived execution capability; token is process-memory only."""

    token: bytes = field(repr=False)
    execution_id: str
    attempt_id: str
    org_id: str
    workspace_id: str
    worker_id: str
    lease_generation: int


@dataclass(frozen=True)
class WorkerWorkspaceCapability:
    """Short-lived capability for one bounded workspace maintenance lease."""

    token: bytes = field(repr=False)
    org_id: str
    workspace_id: str
    worker_id: str
    lease_seconds: int = 300


def claim_worker_maintenance_scope(
    db: Session, *, worker_id: str, after_workspace_id: str | None = None,
    lease_seconds: int = 300,
) -> WorkerWorkspaceCapability | None:
    """Claim one workspace maintenance lease without returning a tenant inventory."""
    if not isinstance(worker_id, str) or not worker_id.strip() or len(worker_id) > 160:
        raise ValueError("worker_id must contain 1-160 characters")
    if not isinstance(lease_seconds, int) or isinstance(lease_seconds, bool) or not 15 <= lease_seconds <= 300:
        raise ValueError("maintenance lease_seconds must be an integer between 15 and 300")
    if after_workspace_id is not None and (
        not isinstance(after_workspace_id, str) or not after_workspace_id or len(after_workspace_id) > 36
    ):
        raise ValueError("after_workspace_id must be a workspace ID of at most 36 characters")
    if db.get_bind().dialect.name != "postgresql":
        raise RuntimeError("Database-verified worker capabilities require PostgreSQL")

    token = secrets.token_bytes(32)
    row = db.execute(
        text("""
            SELECT org_id, workspace_id
            FROM agency_os_private.claim_worker_maintenance_scope(
                :worker_id, :lease_seconds, :token_hash, :after_workspace_id
            )
        """),
        {
            "worker_id": worker_id,
            "lease_seconds": lease_seconds,
            "token_hash": hashlib.sha256(token).digest(),
            "after_workspace_id": after_workspace_id,
        },
    ).mappings().one_or_none()
    if row is None:
        return None
    return WorkerWorkspaceCapability(
        token=token, org_id=row["org_id"],
        workspace_id=row["workspace_id"], worker_id=worker_id,
        lease_seconds=lease_seconds,
    )


def invalidate_worker_execution_capability(db: Session) -> None:
    """Revoke the current execution token after terminal state is flushed."""
    if db.get_bind().dialect.name != "postgresql":
        return
    if "agency_os_worker_capability" not in db.info:
        return
    invalidated = db.execute(text(
        "SELECT agency_os_private.invalidate_worker_execution_capability()"
    )).scalar_one()
    if invalidated is not True:
        raise LeaseExpired("Worker execution capability could not be revoked")


def claim_worker_execution_capability(
    db: Session, *, worker_id: str, lease_seconds: int = 60,
) -> WorkerExecutionCapability | None:
    """Atomically claim one execution and issue a hash-bound DB capability.

    The worker never selects a tenant or execution. PostgreSQL chooses the next
    eligible execution and persists the attempt, capability hash, and audit row
    in one SECURITY DEFINER transaction.
    """
    if not isinstance(worker_id, str) or not worker_id.strip() or len(worker_id) > 160:
        raise ValueError("worker_id must contain 1-160 characters")
    _validate_lease_seconds(lease_seconds)
    if db.get_bind().dialect.name != "postgresql":
        raise RuntimeError("Database-verified worker capabilities require PostgreSQL")

    token = secrets.token_bytes(32)
    row = db.execute(
        text("""
            SELECT execution_id, attempt_id, org_id, workspace_id, lease_generation
            FROM agency_os_private.claim_worker_execution(
                :worker_id, :lease_seconds, :token_hash
            )
        """),
        {
            "worker_id": worker_id,
            "lease_seconds": lease_seconds,
            "token_hash": hashlib.sha256(token).digest(),
        },
    ).mappings().one_or_none()
    if row is None:
        return None
    return WorkerExecutionCapability(
        token=token,
        execution_id=row["execution_id"],
        attempt_id=row["attempt_id"],
        org_id=row["org_id"],
        workspace_id=row["workspace_id"],
        worker_id=worker_id,
        lease_generation=row["lease_generation"],
    )


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
    if (
        not isinstance(lease_seconds, int)
        or isinstance(lease_seconds, bool)
        or not 15 <= lease_seconds <= 3600
    ):
        raise ValueError("lease_seconds must be an integer between 15 and 3600")


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
    _sync_task_delegation(db, execution, "running")

    if execution.started_at is None:
        execution.started_at = now

    execution.last_attempt_at = now
    _sync_plan_draft_execution(db, execution, "running")

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



def _record_provider_usage_observation(
    db: Session,
    execution: Execution,
    attempt: ExecutionAttempt,
    usage: dict | None,
    *,
    source: str,
) -> str | None:
    """Append a tamper-evident, normalized provider usage snapshot to the audit stream."""
    normalized = _validate_provider_usage(usage)
    if normalized is None:
        return None
    if source not in {
        "runtime_result",
        "failure_result",
        "provider_session_reconciliation",
    }:
        raise ValueError("Unsupported provider usage observation source")

    canonical = json.dumps(
        normalized, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    snapshot_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    existing_payloads = (
        db.query(AuditEvent.payload)
        .filter(
            AuditEvent.org_id == execution.org_id,
            AuditEvent.workspace_id == execution.workspace_id,
            AuditEvent.event_type == "execution.provider_usage_observed",
            AuditEvent.resource_type == "execution_attempt",
            AuditEvent.resource_id == attempt.id,
        )
        .all()
    )
    if any(
        isinstance(row[0], dict)
        and row[0].get("snapshot_sha256") == snapshot_hash
        for row in existing_payloads
    ):
        return snapshot_hash

    record_event(
        db,
        execution.org_id,
        None,
        "execution.provider_usage_observed",
        "execution_attempt",
        attempt.id,
        execution.workspace_id,
        {
            "execution_id": execution.id,
            "attempt_number": attempt.attempt_number,
            "provider": attempt.runtime,
            "provider_session_id": attempt.external_run_id,
            "source": source,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "snapshot_sha256": snapshot_hash,
            "usage": normalized,
        },
    )
    return snapshot_hash



def _aggregate_provider_usage(db: Session, execution_id: str) -> dict | None:
    """Aggregate attempt deltas and one latest cumulative snapshot per Managed Agents session.

    Managed Agents usage is session-cumulative. A resumed execution can therefore
    persist the same session's cumulative snapshot on multiple attempts; summing
    those snapshots would double-count prior turns. Distinct provider sessions
    remain additive. Other runtimes retain the existing per-attempt additive
    contract until their usage semantics are explicitly defined.
    """
    rows = (
        db.query(ExecutionAttempt)
        .filter_by(execution_id=execution_id)
        .order_by(ExecutionAttempt.attempt_number.asc(), ExecutionAttempt.id.asc())
        .all()
    )
    additive_usage_rows = []
    managed_session_snapshots: dict[str, tuple[int, dict]] = {}
    for attempt in rows:
        result = attempt.result
        usage = result.get("usage") if isinstance(result, dict) else None
        if usage is None:
            continue
        normalized = _validate_provider_usage(usage)
        if attempt.runtime == "claude_managed_agents" and attempt.external_run_id:
            current = managed_session_snapshots.get(attempt.external_run_id)
            if current is None or attempt.attempt_number >= current[0]:
                managed_session_snapshots[attempt.external_run_id] = (
                    attempt.attempt_number, normalized,
                )
        else:
            additive_usage_rows.append(normalized)

    usage_rows = additive_usage_rows + [
        snapshot for _, snapshot in managed_session_snapshots.values()
    ]
    if not usage_rows:
        return None
    totals: dict = {}
    for key in ("input_tokens", "output_tokens", "cache_read_input_tokens",
                "cache_creation_input_tokens", "list_cost_minor"):
        values = [item[key] for item in usage_rows if key in item]
        if values:
            totals[key] = sum(values)
    active_values = [item["active_seconds"] for item in usage_rows if "active_seconds" in item]
    if active_values:
        totals["active_seconds"] = sum(active_values)
    tool_rows = [item["server_tool_use"] for item in usage_rows if "server_tool_use" in item]
    if tool_rows:
        totals["server_tool_use"] = {
            key: sum(row.get(key, 0) for row in tool_rows)
            for key in ("web_search_requests", "web_fetch_requests")
        }
    if "list_cost_minor" in totals:
        totals["currency"] = "USD"
    return totals or None


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
    metadata = dict(execution.request_metadata or {})
    metadata.pop("control_request", None)
    execution.request_metadata = metadata
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
    db.flush()
    _record_provider_usage_observation(
        db, execution, attempt, result.get("usage"), source="runtime_result",
    )
    aggregated_usage = _aggregate_provider_usage(db, execution.id)
    if aggregated_usage is not None:
        execution.result = dict(result)
        execution.result["usage"] = aggregated_usage
    _sync_task_delegation(db, execution, "succeeded")
    _sync_plan_draft_execution(db, execution, "succeeded")

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
    db.flush()
    invalidate_worker_execution_capability(db)

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
    provider_usage: dict | None = None,
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
    provider_usage = _validate_provider_usage(provider_usage)
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
    if provider_usage is not None:
        usage_result = {"usage": provider_usage}
        execution.result = usage_result
        attempt.result = usage_result

    attempt.status = ExecutionAttemptStatus.failed
    attempt.finished_at = now
    attempt.lease_expires_at = None
    attempt.heartbeat_at = now
    attempt.error_code = error_code
    attempt.error_message = error_message
    db.flush()
    if provider_usage is not None:
        _record_provider_usage_observation(
            db, execution, attempt, provider_usage, source="failure_result",
        )
    aggregated_usage = _aggregate_provider_usage(db, execution.id)
    if aggregated_usage is not None:
        execution.result = {"usage": aggregated_usage}

    retry_scheduled = (
        retryable and execution.attempt_count < execution.max_attempts
    )

    if retry_scheduled:
        _sync_task_delegation(db, execution, "queued", error_code)
        _sync_plan_draft_execution(db, execution, "queued", error_code)
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
        _sync_task_delegation(db, execution, "failed", error_code)
        _sync_plan_draft_execution(db, execution, "failed", error_code)

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
    db.flush()
    invalidate_worker_execution_capability(db)

    return execution, attempt


def queue_ready_delegations(db: Session, *, limit: int = 100) -> int:
    """Create idempotent OS executions for eligible, dependency-ready agent tasks.

    This function only persists execution requests. It never calls a provider;
    the existing worker claims and executes the resulting durable records.
    """
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
        raise ValueError("limit must be an integer between 1 and 1000")

    from app.execution_service import create_execution, ExecutionServiceError

    candidates = (
        db.query(Delegation)
        .filter(Delegation.status.in_(("ready", "blocked")))
        .filter(Delegation.last_error_code.is_(None))
        .order_by(Delegation.created_at.asc(), Delegation.id.asc())
        .with_for_update(skip_locked=True)
        .limit(limit)
        .all()
    )
    queued = 0
    for row in candidates:
        task = db.query(Task).filter_by(
            id=row.child_task_id, org_id=row.org_id,
            workspace_id=row.workspace_id,
        ).with_for_update().first()
        assignee = db.query(WorkforceMember).filter_by(
            id=row.assigned_to_member_id, org_id=row.org_id,
            workspace_id=row.workspace_id,
        ).first()
        if task is None or assignee is None:
            row.status = "failed"
            row.last_error_code = "DELEGATION_RESOURCE_MISSING"
            continue
        if row.dependency_task_id:
            dependency = db.query(Task).filter_by(
                id=row.dependency_task_id, org_id=row.org_id,
                workspace_id=row.workspace_id,
            ).first()
            if dependency is None or dependency.status in {"failed", "cancelled"}:
                task.status = "failed"
                row.status = "failed"
                row.last_error_code = "DEPENDENCY_FAILED"
                record_event(db, row.org_id, None,
                             "workforce.delegated_task_dependency_failed",
                             "delegation", row.id, row.workspace_id,
                             {"dependency_task_id": row.dependency_task_id})
                continue
            if dependency.status not in {"succeeded", "completed", "done"}:
                task.status = "blocked"
                row.status = "blocked"
                continue
        if assignee.status != "active" or assignee.is_founder_reserved:
            task.status = "blocked"
            row.status = "blocked"
            row.last_error_code = "ASSIGNEE_NOT_ACTIVE"
            continue
        # Human assignments remain visible in the plan for manual handling.
        if not assignee.agent_id:
            # Human-owned tasks enter the manual work queue, not the AI worker queue.
            row.status = "queued"
            task.status = "queued"
            continue
        try:
            execution = create_execution(
                db, org_id=row.org_id, workspace_id=row.workspace_id,
                task_id=task.id, agent_id=assignee.agent_id,
                requested_by=task.created_by,
                idempotency_key=f"delegation:{row.id}",
            )
        except ExecutionServiceError as exc:
            row.status = "blocked"
            task.status = "blocked"
            row.last_error_code = type(exc).__name__
            record_event(db, row.org_id, None,
                         "workforce.delegated_task_queue_blocked",
                         "delegation", row.id, row.workspace_id,
                         {"error_code": row.last_error_code})
            continue
        row.status = "queued"
        task.status = "queued"
        record_event(db, row.org_id, None,
                     "workforce.delegated_task_execution_queued",
                     "delegation", row.id, row.workspace_id,
                     {"execution_id": execution.id, "task_id": task.id,
                      "assignee_member_id": assignee.id})
        queued += 1
    if candidates:
        db.flush()
    return queued


def promote_due_retries(
    db: Session,
    *,
    limit: int = 100,
) -> int:
    """
    Move due retry_wait executions back to queued within one authorized workspace.

    PostgreSQL workers invoke this only inside a verified maintenance-scope
    transaction. Execution claiming uses claim_worker_execution_capability().
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
            _sync_task_delegation(db, execution, "queued", error_code)
            _sync_plan_draft_execution(db, execution, "queued", error_code)
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
            _sync_task_delegation(db, execution, "failed", error_code)
            _sync_plan_draft_execution(db, execution, "failed", error_code)

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
