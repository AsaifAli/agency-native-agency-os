
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.audit import record_event
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
) -> bool:
    return (
        existing.workspace_id == workspace_id
        and existing.task_id == task_id
        and existing.agent_id == agent_id
        and existing.requested_by == requested_by
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
) -> Execution:
    """
    Create a queued execution.

    The caller owns the transaction and must commit or roll back.
    This function never dispatches work or calls an AI provider.
    """

    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

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

    _validate_runtime_policy(agent)

    execution = Execution(
        org_id=org_id,
        workspace_id=workspace_id,
        task_id=task.id,
        agent_id=agent.id,
        requested_by=requested_by,
        idempotency_key=idempotency_key,
        runtime=agent.runtime,
        data_class=agent.data_class,
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
            "runtime": agent.runtime,
            "data_class": agent.data_class.value,
        },
    )

    return execution
