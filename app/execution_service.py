
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.audit import record_event
from app.agent_registry_service import ensure_initial_agent_version
from app.models import (
    Agent,
    DataClass,
    Execution,
    ExecutionStatus,
    Task,
    Workspace,
)
from app.policy import assert_managed_agents_eligible
from app.integrations.runtime_registry import is_runtime_available
from app.workforce_models import WorkforceMember, WorkforceCapability


class ExecutionServiceError(Exception):
    """Base exception for execution service errors."""


class ResourceNotFound(ExecutionServiceError):
    pass


class ExecutionConflict(ExecutionServiceError):
    pass


class AgentNotEnabled(ExecutionServiceError):
    pass


class PolicyViolation(ExecutionServiceError):
    pass


def _validate_runtime_policy(agent: Agent) -> None:
    # Reject unavailable runtimes before queueing. This registry is shared
    # with the worker factory so API and worker capabilities cannot drift.
    if not is_runtime_available(agent.runtime):
        raise PolicyViolation(
            "The agent runtime is not configured for this environment"
        )

    if agent.runtime == "mock" and agent.data_class != DataClass.synthetic:
        raise PolicyViolation(
            "The mock runtime is restricted to synthetic data"
        )

    # No confidential or regulated workload is eligible until an
    # alternative runtime has been explicitly assessed and approved.
    if agent.data_class in {DataClass.confidential, DataClass.regulated}:
        raise PolicyViolation(
            "No approved runtime route is configured for this data class"
        )

    # Client authorization must come from a trusted backend process.
    # It is deliberately not accepted as a caller-provided value here.
    if agent.data_class == DataClass.commercial:
        raise PolicyViolation(
            "Commercial data requires documented client authorization "
            "through an approved backend process"
        )

    if agent.runtime == "claude_managed_agents":
        try:
            assert_managed_agents_eligible(
                agent.data_class,
                client_authorized=False,
            )
        except HTTPException as exc:
            raise PolicyViolation(str(exc)) from exc


def _same_request(
    existing: Execution,
    *,
    workspace_id: str,
    task_id: str,
    agent_id: str,
    requested_by: str,
    required_capability_action: str | None,
) -> bool:
    if required_capability_action is None:
        capability_matches = existing.required_capability_action in {
            None, "task.execute", "research.execute", "report.generate",
        }
    else:
        capability_matches = (
            existing.required_capability_action == required_capability_action
        )
    return (
        existing.workspace_id == workspace_id
        and existing.task_id == task_id
        and existing.agent_id == agent_id
        and existing.requested_by == requested_by
        and capability_matches
    )


def create_execution(
    db: Session,
    *,
    org_id: str,
    workspace_id: str,
    task_id: str,
    agent_id: str,
    requested_by: str,
    idempotency_key: str,
    max_attempts: int = 3,
    required_capability_action: str | None = None,
) -> Execution:
    """
    Create a queued execution.

    The caller owns the transaction and must commit or roll back.
    This function never dispatches work or calls an AI provider.
    """

    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    if required_capability_action not in (
        None, "task.execute", "research.execute", "report.generate", "plan.generate"
    ):
        raise ValueError("Unsupported execution capability action")
    required_actions = (
        {required_capability_action}
        if required_capability_action is not None
        else {"task.execute", "research.execute", "report.generate"}
    )

    # Check for an existing request first. Repeated requests with the
    # same key and same identity return the original execution.
    existing = (
        db.query(Execution)
        .filter_by(
            org_id=org_id,
            idempotency_key=idempotency_key,
        )
        .first()
    )

    if existing:
        if not _same_request(
            existing,
            workspace_id=workspace_id,
            task_id=task_id,
            agent_id=agent_id,
            requested_by=requested_by,
            required_capability_action=required_capability_action,
        ):
            raise ExecutionConflict(
                "Idempotency key was already used for a different execution"
            )
        return existing

    # Validate every resource within the requested organization and
    # workspace. Do not trust IDs supplied by the caller independently.
    workspace = (
        db.query(Workspace)
        .filter_by(id=workspace_id, org_id=org_id)
        .first()
    )
    if not workspace:
        raise ResourceNotFound("Workspace not found")

    task = (
        db.query(Task)
        .filter_by(
            id=task_id,
            org_id=org_id,
            workspace_id=workspace_id,
        )
        .first()
    )
    if not task:
        raise ResourceNotFound("Task not found")

    agent = (
        db.query(Agent)
        .filter_by(
            id=agent_id,
            org_id=org_id,
            workspace_id=workspace_id,
        )
        .first()
    )
    if not agent:
        raise ResourceNotFound("Agent not found")

    if not agent.enabled:
        raise AgentNotEnabled("Agent is not enabled for execution")

    workforce_member = db.query(WorkforceMember).filter_by(
        org_id=org_id, workspace_id=workspace_id, agent_id=agent.id
    ).one_or_none()
    if workforce_member is not None:
        if workforce_member.status != "active" or workforce_member.is_founder_reserved:
            raise AgentNotEnabled("Workforce member is not active for execution")
        grants = db.query(WorkforceCapability).filter_by(
            org_id=org_id, workspace_id=workspace_id,
            member_id=workforce_member.id, enabled=True,
        ).all()
        eligible_grant = None
        effective_capability_action = required_capability_action
        for grant in sorted(grants, key=lambda item: (item.capability_key, item.id)):
            eligible_actions = sorted(
                set(grant.allowed_actions or []) & required_actions
            )
            if (
                agent.data_class.value in (grant.allowed_data_classes or [])
                and eligible_actions
                and not (grant.tool_allowlist or [])
            ):
                eligible_grant = grant
                if effective_capability_action is None:
                    effective_capability_action = eligible_actions[0]
                break
        if eligible_grant is None:
            raise AgentNotEnabled(
                "Workforce member requires an enabled data-eligible execution capability with no ungoverned tools"
            )
    else:
        effective_capability_action = required_capability_action or "task.execute"

    agent_version = ensure_initial_agent_version(db, agent, created_by=requested_by)
    _validate_runtime_policy(agent)

    execution = Execution(
        org_id=org_id,
        workspace_id=workspace_id,
        task_id=task.id,
        agent_id=agent.id,
        agent_version_id=agent_version.id,
        required_capability_action=effective_capability_action,
        requested_by=requested_by,
        idempotency_key=idempotency_key,
        runtime=agent_version.runtime,
        data_class=agent_version.data_class,
        client_authorized=False,
        status=ExecutionStatus.queued,
        attempt_count=0,
        max_attempts=max_attempts,
        request_metadata={},
    )

    # The database unique constraint is the final protection against
    # concurrent requests racing with the same organization/key pair.
    try:
        with db.begin_nested():
            db.add(execution)
            db.flush()
    except IntegrityError:
        existing = (
            db.query(Execution)
            .filter_by(
                org_id=org_id,
                idempotency_key=idempotency_key,
            )
            .first()
        )
        if existing is None:
            raise

        if not _same_request(
            existing,
            workspace_id=workspace_id,
            task_id=task_id,
            agent_id=agent_id,
            requested_by=requested_by,
        ):
            raise ExecutionConflict(
                "Idempotency key was already used for a different execution"
            )
        return existing

    record_event(
        db,
        org_id,
        requested_by,
        "execution.queued",
        "execution",
        execution.id,
        workspace_id,
        {
            "task_id": task.id,
            "agent_id": agent.id,
            "agent_version_id": agent_version.id,
            "agent_version_sha256": agent_version.config_sha256,
            "required_capability_action": effective_capability_action,
            "runtime": agent_version.runtime,
            "data_class": agent_version.data_class.value,
        },
    )

    return execution

def current_execution_authorization_error(
    db: Session,
    execution: Execution,
    agent: Agent,
) -> tuple[str, str] | None:
    """Recheck live kill switches and capability grants immediately before runtime start."""
    if not agent.enabled:
        return ("AGENT_DISABLED", "Agent was disabled after this execution was queued.")

    member = db.query(WorkforceMember).filter_by(
        org_id=execution.org_id,
        workspace_id=execution.workspace_id,
        agent_id=agent.id,
    ).one_or_none()
    if member is None:
        return None  # Legacy non-workforce agents have no WorkforceCapability record.
    if member.status != "active" or member.is_founder_reserved:
        return (
            "WORKFORCE_MEMBER_INACTIVE",
            "Workforce membership was disabled or reserved after this execution was queued.",
        )

    required_actions = (
        {execution.required_capability_action}
        if execution.required_capability_action
        else {"task.execute", "research.execute", "report.generate"}
    )
    grants = db.query(WorkforceCapability).filter_by(
        org_id=execution.org_id,
        workspace_id=execution.workspace_id,
        member_id=member.id,
        enabled=True,
    ).all()
    eligible = any(
        execution.data_class.value in (grant.allowed_data_classes or [])
        and bool(set(grant.allowed_actions or []) & required_actions)
        and not (grant.tool_allowlist or [])
        for grant in grants
    )
    if not eligible:
        return (
            "WORKFORCE_CAPABILITY_REVOKED",
            "No current enabled capability authorizes this execution's action and data class.",
        )
    return None

