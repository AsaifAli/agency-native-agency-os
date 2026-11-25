"""Build a least-privilege callback from Managed Agents custom tools to the OS gateway."""
import hashlib
from datetime import datetime, timezone
from typing import Callable

from fastapi import HTTPException

from app.integrations.runtime import ExecutionRequest
from app.machine_identity import MachinePrincipal, create_agent_session
from app.models import Execution
from app.security_models import AgentSession, MachineIdentity
from app.tool_gateway import invoke_registered_tool
from app.tool_registry import get_tool_by_provider_name


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class ToolExecutionRejected(Exception):
    """A custom tool call was rejected by OS identity or policy controls."""


def build_machine_tool_executor(
    *,
    session_factory: Callable,
    request: ExecutionRequest,
    execution_id: str,
    session_ttl_seconds: int,
) -> Callable[[str, dict, str], dict]:
    """Return a callback that lazily creates/reuses a durable session per execution."""
    ttl_seconds = max(60, min(int(session_ttl_seconds), 86400))

    def execute(provider_tool_name: str, payload: dict, provider_event_id: str) -> dict:
        spec = get_tool_by_provider_name(provider_tool_name)
        if spec is None:
            raise ToolExecutionRejected("TOOL_NOT_REGISTERED")
        if not isinstance(provider_event_id, str) or not provider_event_id or len(provider_event_id) > 200:
            raise ToolExecutionRejected("INVALID_PROVIDER_TOOL_EVENT")

        digest = hashlib.sha256(
            f"{provider_tool_name}:{provider_event_id}".encode("utf-8")
        ).hexdigest()
        idempotency_key = f"ma_{digest}"

        with session_factory() as db:
            identity = (
                db.query(MachineIdentity)
                .filter_by(
                    org_id=request.org_id,
                    workspace_id=request.workspace_id,
                    subject_type="agent",
                    subject_id=request.agent_id,
                )
                .with_for_update()
                .first()
            )
            now = datetime.now(timezone.utc)
            if (
                identity is None
                or identity.revoked_at is not None
                or _as_utc(identity.expires_at) <= now
            ):
                raise ToolExecutionRejected("MACHINE_IDENTITY_NOT_ACTIVE")

            execution = (
                db.query(Execution)
                .filter_by(
                    id=execution_id,
                    org_id=request.org_id,
                    workspace_id=request.workspace_id,
                )
                .with_for_update()
                .first()
            )
            if execution is None:
                raise ToolExecutionRejected("EXECUTION_NOT_FOUND")

            session = None
            if execution.machine_session_id:
                session = db.query(AgentSession).filter_by(
                    id=execution.machine_session_id,
                    org_id=request.org_id,
                    workspace_id=request.workspace_id,
                    machine_identity_id=identity.id,
                ).first()
                if (
                    session is not None
                    and session.status == "active"
                    and _as_utc(session.expires_at) > now
                    and session.data_class == request.data_class.value
                ):
                    pass
                else:
                    session = None

            principal = MachinePrincipal(identity=identity)
            if session is None:
                session = create_agent_session(
                    db,
                    principal,
                    purpose=f"Agent execution: {request.task_title or request.task_id}"[:240],
                    data_class=request.data_class.value,
                    ttl_seconds=ttl_seconds,
                )
                execution.machine_session_id = session.id
                db.commit()

            result = invoke_registered_tool(
                db,
                principal,
                session_id=session.id,
                tool_key=spec.key,
                payload=payload,
                idempotency_key=idempotency_key,
            )
            return result["result"]

    return execute
