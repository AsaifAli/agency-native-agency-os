"""Bounded recovery of missing usage from idle Claude Managed Agents sessions.

Provider reads run outside database transactions. Persistence re-locks and
revalidates the abandoned attempt and execution state before recording the
normalized cumulative snapshot.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy.orm import Session

from app.audit import record_event
from app.models import (
    Execution,
    ExecutionAttempt,
    ExecutionAttemptStatus,
    ExecutionStatus,
)
from app.worker_service import _aggregate_provider_usage, _validate_provider_usage

logger = logging.getLogger(__name__)
SessionFactory = Callable[[], Session]
RECONCILIATION_RETRY_SECONDS = 300
MAX_RECONCILIATION_BATCH = 100


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _recently_checked(result: dict, now: datetime) -> bool:
    marker = result.get("usage_reconciliation")
    if not isinstance(marker, dict) or marker.get("status") not in {"pending", "reconciled"}:
        return False
    raw = marker.get("checked_at")
    if not isinstance(raw, str):
        return False
    try:
        checked_at = _utc(datetime.fromisoformat(raw))
    except ValueError:
        return False
    return now - checked_at < timedelta(seconds=RECONCILIATION_RETRY_SECONDS)


def _persist_snapshot(
    session_factory: SessionFactory,
    *,
    execution_id: str,
    attempt_id: str,
    external_run_id: str,
    usage: dict | None,
    observed_at: datetime,
    pending_reason: str = "provider_session_not_idle_or_usage_unavailable",
) -> str:
    with session_factory() as db:
        # Keep the same lock order as worker lifecycle operations.
        execution = (
            db.query(Execution)
            .filter(Execution.id == execution_id)
            .with_for_update(skip_locked=True)
            .one_or_none()
        )
        if execution is None or execution.status not in (
            ExecutionStatus.retry_wait,
            ExecutionStatus.failed,
        ):
            return "skipped"

        attempt = (
            db.query(ExecutionAttempt)
            .filter(
                ExecutionAttempt.id == attempt_id,
                ExecutionAttempt.execution_id == execution_id,
            )
            .with_for_update()
            .one_or_none()
        )
        if (
            attempt is None
            or attempt.status != ExecutionAttemptStatus.abandoned
            or attempt.runtime != "claude_managed_agents"
            or attempt.external_run_id != external_run_id
        ):
            return "skipped"

        result = dict(attempt.result or {})
        current_usage = result.get("usage")
        if not isinstance(current_usage, dict):
            current_usage = None

        checked_at = observed_at.isoformat()
        if usage is None:
            marker = dict(result.get("usage_reconciliation") or {})
            marker.update({
                "status": "pending",
                "checked_at": checked_at,
                "reason": pending_reason,
            })
            result["usage_reconciliation"] = marker
            attempt.result = result
            db.commit()
            return "pending"

        normalized = _validate_provider_usage(usage)
        if normalized is None:
            marker = dict(result.get("usage_reconciliation") or {})
            marker.update({
                "status": "pending",
                "checked_at": checked_at,
                "reason": pending_reason,
            })
            result["usage_reconciliation"] = marker
            attempt.result = result
            db.commit()
            return "pending"

        canonical = json.dumps(
            normalized, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        snapshot_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        previous_marker = result.get("usage_reconciliation")
        if (
            current_usage == normalized
            and isinstance(previous_marker, dict)
            and previous_marker.get("snapshot_sha256") == snapshot_hash
        ):
            previous_marker.update({
                "status": "reconciled",
                "checked_at": checked_at,
            })
            result["usage_reconciliation"] = previous_marker
            attempt.result = result
            db.commit()
            return "skipped"

        result["usage"] = normalized
        result["usage_reconciliation"] = {
            "status": "reconciled",
            "source": "provider_session_snapshot",
            "checked_at": checked_at,
            "snapshot_sha256": snapshot_hash,
        }
        attempt.result = result
        db.flush()

        aggregated = _aggregate_provider_usage(db, execution.id)
        if aggregated is not None:
            execution_result = dict(execution.result or {})
            execution_result["usage"] = aggregated
            execution.result = execution_result

        record_event(
            db,
            execution.org_id,
            None,
            "execution.provider_usage_reconciled",
            "execution_attempt",
            attempt.id,
            execution.workspace_id,
            {
                "execution_id": execution.id,
                "provider": "claude_managed_agents",
                "external_run_id": external_run_id,
                "snapshot_sha256": snapshot_hash,
                "list_cost_minor": normalized.get("list_cost_minor"),
                "currency": normalized.get("currency"),
            },
        )
        db.commit()
        return "reconciled"


def reconcile_abandoned_managed_agent_usage(
    session_factory: SessionFactory,
    *,
    runtime,
    limit: int = 10,
    now: datetime | None = None,
) -> dict[str, int]:
    """Reconcile a bounded batch of abandoned sessions without holding DB locks over HTTP."""
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_RECONCILIATION_BATCH:
        raise ValueError(f"limit must be between 1 and {MAX_RECONCILIATION_BATCH}")
    if not callable(getattr(runtime, "fetch_idle_session_usage", None)):
        raise ValueError("runtime must provide fetch_idle_session_usage")

    observed_at = _utc(now or datetime.now(timezone.utc))
    counts = {"reconciled": 0, "pending": 0, "skipped": 0}
    with session_factory() as db:
        rows = (
            db.query(
                ExecutionAttempt.id,
                ExecutionAttempt.execution_id,
                ExecutionAttempt.external_run_id,
                ExecutionAttempt.result,
                ExecutionAttempt.attempt_number,
            )
            .join(Execution, Execution.id == ExecutionAttempt.execution_id)
            .filter(
                Execution.runtime == "claude_managed_agents",
                Execution.status.in_((ExecutionStatus.retry_wait, ExecutionStatus.failed)),
                ExecutionAttempt.runtime == "claude_managed_agents",
                ExecutionAttempt.status == ExecutionAttemptStatus.abandoned,
                ExecutionAttempt.external_run_id.is_not(None),
            )
            .order_by(ExecutionAttempt.finished_at.asc(), ExecutionAttempt.id.asc())
            .limit(1000)
            .all()
        )

    candidates = []
    latest_by_session = {}
    for attempt_id, execution_id, external_run_id, raw_result, attempt_number in rows:
        key = (execution_id, external_run_id)
        current = latest_by_session.get(key)
        if current is None or attempt_number > current[0]:
            latest_by_session[key] = (
                attempt_number, attempt_id, execution_id, external_run_id, raw_result,
            )

    for _number, attempt_id, execution_id, external_run_id, raw_result in latest_by_session.values():
        result = raw_result if isinstance(raw_result, dict) else {}
        if _recently_checked(result, observed_at):
            counts["skipped"] += 1
            continue
        candidates.append((attempt_id, execution_id, external_run_id))
        if len(candidates) >= limit:
            break

    for attempt_id, execution_id, external_run_id in candidates:
        try:
            usage = runtime.fetch_idle_session_usage(external_run_id)
        except Exception as exc:
            # Do not persist exception text: provider errors can contain
            # request metadata. Persist a cooldown marker to bound retries.
            logger.warning(
                "Provider usage reconciliation read failed for attempt %s (%s)",
                attempt_id,
                type(exc).__name__,
            )
            outcome = _persist_snapshot(
                session_factory,
                execution_id=execution_id,
                attempt_id=attempt_id,
                external_run_id=external_run_id,
                usage=None,
                observed_at=observed_at,
                pending_reason="provider_read_failed",
            )
            counts[outcome] += 1
            continue

        try:
            outcome = _persist_snapshot(
                session_factory,
                execution_id=execution_id,
                attempt_id=attempt_id,
                external_run_id=external_run_id,
                usage=usage,
                observed_at=observed_at,
            )
        except (TypeError, ValueError):
            logger.warning(
                "Provider usage reconciliation rejected invalid usage for attempt %s",
                attempt_id,
            )
            outcome = _persist_snapshot(
                session_factory,
                execution_id=execution_id,
                attempt_id=attempt_id,
                external_run_id=external_run_id,
                usage=None,
                observed_at=observed_at,
                pending_reason="invalid_usage_snapshot",
            )
            counts[outcome] += 1
            continue
        counts[outcome] += 1

    return counts
