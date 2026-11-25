"""Build a least-privilege callback from Managed Agents custom tools to the OS gateway."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Callable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.audit import record_event
from app.integrations.runtime import RuntimeToolRejected
from app.machine_identity import MachinePrincipal, create_agent_session
from app.models import Execution, ExecutionAttempt, ExecutionAttemptStatus, ExecutionStatus
from app.security_models import AgentSession, MachineIdentity
from app.tool_gateway import invoke_registered_tool
from app.tool_registry import get_tool_by_provider_name


class ToolExecutionRejected(RuntimeToolRejected):
    """A custom tool call was rejected by OS identity or policy controls."""


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def build_machine_tool_executor(
    *,
    session_factory: Callable[[], Session],
    request,
    execution_id: str,
    attempt_id: str,
    worker_id: str,
    session_ttl_seconds: int,
):
    """Return a callback that revalidates the live execution lease for every tool call."""
    ttl_seconds = max(60, min(int(session_ttl_seconds), 86400))

    def execute(provider_tool_name: str, payload: dict, provider_event_id: str) -> dict:
        spec = get_tool_by_provider_name(provider_tool_name)
        if spec is None:
            raise ToolExecutionRejected("TOOL_NOT_REGISTERED")
        if (
            not isinstance(provider_event_id, str)
            or not re.fullmatch(r"sevt_[A-Za-z0-9_-]{1,190}", provider_event_id)
        ):
            raise ToolExecutionRejected("INVALID_PROVIDER_TOOL_EVENT")

        # Provider event IDs are unique within a provider session, not necessarily
        # across sessions. Include the OS execution ID in the idempotency namespace.
        digest = hashlib.sha256(
            f"{execution_id}:{provider_tool_name}:{provider_event_id}".encode("utf-8")
        ).hexdigest()
        idempotency_key = f"ma_{digest}"

        with session_factory() as db:
            # Keep the same lock order as worker lease operations: execution, attempt,
            # then machine identity. A stale worker must not invoke tools after lease loss.
            execution = (
                db.query(Execution)
                .filter_by(id=execution_id, org_id=request.org_id, workspace_id=request.workspace_id)
                .with_for_update()
                .first()
            )
            if execution is None:
                raise ToolExecutionRejected("EXECUTION_NOT_FOUND")
            if (
                execution.status != ExecutionStatus.running
                or execution.agent_id != request.agent_id
                or execution.data_class != request.data_class
            ):
                raise ToolExecutionRejected("EXECUTION_NOT_ACTIVE")

            attempt = (
                db.query(ExecutionAttempt)
                .filter_by(id=attempt_id, execution_id=execution_id)
                .with_for_update()
                .first()
            )
            now = datetime.now(timezone.utc)
            if (
                attempt is None
                or attempt.status != ExecutionAttemptStatus.running
                or attempt.worker_id != worker_id
                or attempt.lease_expires_at is None
                or _as_utc(attempt.lease_expires_at) <= now
                or attempt.runtime != execution.runtime
            ):
                raise ToolExecutionRejected("EXECUTION_ATTEMPT_NOT_ACTIVE")

            # Read the session's identity reference without locking, then lock identity
            # before session. This matches revoke/authz lock order and avoids deadlocks.
            session_identity_id = None
            if execution.machine_session_id:
                session_identity_id = (
                    db.query(AgentSession.machine_identity_id)
                    .filter_by(
                        id=execution.machine_session_id,
                        org_id=request.org_id,
                        workspace_id=request.workspace_id,
                    )
                    .scalar()
                )
                if session_identity_id is None:
                    raise ToolExecutionRejected("EXECUTION_MACHINE_SESSION_INVALID")

            identity_query = db.query(MachineIdentity).filter_by(
                org_id=request.org_id,
                workspace_id=request.workspace_id,
                subject_type="agent",
                subject_id=request.agent_id,
                revoked_at=None,
            )
            if session_identity_id is not None:
                identity_query = identity_query.filter(MachineIdentity.id == session_identity_id)
            else:
                identity_query = identity_query.order_by(
                    MachineIdentity.created_at.desc(), MachineIdentity.id.desc()
                )
            identity = identity_query.with_for_update().first()
            if identity is None or _as_utc(identity.expires_at) <= now:
                raise ToolExecutionRejected("MACHINE_IDENTITY_NOT_ACTIVE")

            session = None
            if execution.machine_session_id:
                session = (
                    db.query(AgentSession)
                    .filter_by(
                        id=execution.machine_session_id,
                        org_id=request.org_id,
                        workspace_id=request.workspace_id,
                        machine_identity_id=identity.id,
                    )
                    .with_for_update()
                    .first()
                )
                if session is None:
                    raise ToolExecutionRejected("EXECUTION_MACHINE_SESSION_INVALID")

            principal = MachinePrincipal(identity=identity)
            if session is not None:
                if session.status == "active" and _as_utc(session.expires_at) > now:
                    if session.data_class != request.data_class.value:
                        session.status = "cancelled"
                        session.ended_at = now
                        record_event(
                            db,
                            identity.org_id,
                            None,
                            "agent_session.cancelled",
                            "agent_session",
                            session.id,
                            identity.workspace_id,
                            {
                                "machine_identity_id": identity.id,
                                "reason_code": "EXECUTION_DATA_CLASS_CHANGED",
                            },
                        )
                        session = None
                else:
                    if session.status == "active":
                        session.status = "expired"
                        session.ended_at = now
                        record_event(
                            db,
                            identity.org_id,
                            None,
                            "agent_session.expired",
                            "agent_session",
                            session.id,
                            identity.workspace_id,
                            {
                                "machine_identity_id": identity.id,
                                "reason_code": "SESSION_TTL_EXPIRED",
                            },
                        )
                    session = None

            if session is None:
                session = create_agent_session(
                    db,
                    principal,
                    purpose=f"Agent execution: {request.task_title or request.task_id}"[:240],
                    data_class=request.data_class.value,
                    ttl_seconds=ttl_seconds,
                )
                execution.machine_session_id = session.id

            # invoke_registered_tool owns the commit. Session binding, tool result,
            # invocation record and success audit therefore commit atomically.
            try:
                result = invoke_registered_tool(
                    db,
                    principal,
                    session_id=session.id,
                    tool_key=spec.key,
                    payload=payload,
                    idempotency_key=idempotency_key,
                )
            except HTTPException as exc:
                raise ToolExecutionRejected("OS_TOOL_CALL_REJECTED") from exc
            return result["result"]

    return execute
