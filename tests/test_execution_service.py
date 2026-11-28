
import uuid

import pytest

from app.db import Base, SessionLocal, engine
from app.execution_service import (
    AgentNotEnabled,
    ExecutionConflict,
    PolicyViolation,
    ResourceNotFound,
    create_execution,
)
from app.config import settings
from app.models import (
    Agent,
    AuditEvent,
    DataClass,
    Organization,
    Task,
    User,
    Workspace,
)


@pytest.fixture
def execution_context(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(settings, "mock_runtime_enabled", True)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    suffix = uuid.uuid4().hex[:10]

    user = User(
        email=f"execution-{suffix}@test.local",
        display_name="Execution Test",
    )
    org = Organization(name=f"Execution Org {suffix}")
    other_org = Organization(name=f"Other Org {suffix}")

    db.add_all([user, org, other_org])
    db.flush()

    workspace = Workspace(
        id=f"ws-{suffix}",
        org_id=org.id,
        name="Execution Workspace",
    )
    other_workspace = Workspace(
        id=f"other-ws-{suffix}",
        org_id=other_org.id,
        name="Other Workspace",
    )
    db.add_all([workspace, other_workspace])
    db.flush()

    agent = Agent(
        org_id=org.id,
        workspace_id=workspace.id,
        name="Test Agent",
        runtime="mock",
        data_class=DataClass.synthetic,
        enabled=True,
    )
    other_agent = Agent(
        org_id=other_org.id,
        workspace_id=other_workspace.id,
        name="Other Agent",
        runtime="mock",
        data_class=DataClass.synthetic,
        enabled=True,
    )
    task = Task(
        org_id=org.id,
        workspace_id=workspace.id,
        title="Test Task",
        description="Synthetic test task",
        created_by=user.id,
    )
    other_task = Task(
        org_id=other_org.id,
        workspace_id=other_workspace.id,
        title="Other Task",
        created_by=user.id,
    )

    db.add_all([agent, other_agent, task, other_task])
    db.commit()

    context = {
        "db": db,
        "org_id": org.id,
        "other_org_id": other_org.id,
        "workspace_id": workspace.id,
        "other_workspace_id": other_workspace.id,
        "user_id": user.id,
        "agent_id": agent.id,
        "other_agent_id": other_agent.id,
        "task_id": task.id,
        "other_task_id": other_task.id,
    }

    try:
        yield context
    finally:
        db.rollback()
        db.close()


def create_test_execution(ctx, **overrides):
    args = {
        "org_id": ctx["org_id"],
        "workspace_id": ctx["workspace_id"],
        "task_id": ctx["task_id"],
        "agent_id": ctx["agent_id"],
        "requested_by": ctx["user_id"],
        "idempotency_key": f"exec-{uuid.uuid4().hex}",
    }
    args.update(overrides)
    return create_execution(ctx["db"], **args)


def test_create_execution_queues_and_audits(execution_context):
    ctx = execution_context

    execution = create_test_execution(ctx)
    ctx["db"].commit()
    ctx["db"].refresh(execution)

    assert execution.status.value == "queued"
    assert execution.attempt_count == 0
    assert execution.max_attempts == 3
    assert execution.runtime == "mock"
    assert execution.data_class == DataClass.synthetic
    assert execution.client_authorized is False
    assert execution.request_metadata == {}

    event = (
        ctx["db"].query(AuditEvent)
        .filter_by(
            org_id=ctx["org_id"],
            resource_type="execution",
            resource_id=execution.id,
            event_type="execution.queued",
        )
        .one()
    )
    assert event.actor_user_id == ctx["user_id"]
    assert event.workspace_id == ctx["workspace_id"]


def test_same_idempotency_key_returns_existing_execution(execution_context):
    ctx = execution_context
    key = f"same-{uuid.uuid4().hex}"

    first = create_test_execution(ctx, idempotency_key=key)
    ctx["db"].commit()

    second = create_test_execution(ctx, idempotency_key=key)

    assert second.id == first.id


def test_idempotency_key_conflict_is_rejected(execution_context):
    ctx = execution_context
    key = f"conflict-{uuid.uuid4().hex}"

    create_test_execution(ctx, idempotency_key=key)
    ctx["db"].commit()

    with pytest.raises(ExecutionConflict):
        create_test_execution(
            ctx,
            idempotency_key=key,
            task_id=ctx["other_task_id"],
        )


def test_task_from_another_tenant_is_rejected(execution_context):
    ctx = execution_context

    with pytest.raises(ResourceNotFound):
        create_test_execution(ctx, task_id=ctx["other_task_id"])


def test_agent_from_another_tenant_is_rejected(execution_context):
    ctx = execution_context

    with pytest.raises(ResourceNotFound):
        create_test_execution(ctx, agent_id=ctx["other_agent_id"])


def test_disabled_agent_is_rejected(execution_context):
    ctx = execution_context
    agent = ctx["db"].get(Agent, ctx["agent_id"])
    agent.enabled = False
    ctx["db"].commit()

    with pytest.raises(AgentNotEnabled):
        create_test_execution(ctx)


def test_unconfigured_claude_runtime_is_rejected_before_queueing(execution_context):
    ctx = execution_context
    agent = ctx["db"].get(Agent, ctx["agent_id"])
    agent.runtime = "claude_managed_agents"
    ctx["db"].commit()

    with pytest.raises(PolicyViolation, match="not configured"):
        create_test_execution(ctx)


def test_mock_runtime_is_rejected_when_disabled(execution_context, monkeypatch):
    ctx = execution_context
    monkeypatch.setattr(settings, "mock_runtime_enabled", False)

    with pytest.raises(PolicyViolation, match="not configured"):
        create_test_execution(ctx)


def test_mock_runtime_is_restricted_to_synthetic_data(execution_context):
    ctx = execution_context
    agent = ctx["db"].get(Agent, ctx["agent_id"])
    agent.data_class = DataClass.commercial
    ctx["db"].commit()

    with pytest.raises(PolicyViolation, match="synthetic data"):
        create_test_execution(ctx)


@pytest.mark.parametrize(
    "data_class",
    [
        DataClass.commercial,
        DataClass.confidential,
        DataClass.regulated,
    ],
)
def test_restricted_data_classes_are_rejected(execution_context, data_class):
    ctx = execution_context
    agent = ctx["db"].get(Agent, ctx["agent_id"])
    agent.data_class = data_class
    ctx["db"].commit()

    with pytest.raises(PolicyViolation):
        create_test_execution(ctx)



def test_create_execution_pins_immutable_agent_version(execution_context):
    from app.models import AgentVersion

    ctx = execution_context
    execution = create_test_execution(ctx)
    ctx["db"].commit()
    ctx["db"].refresh(execution)

    agent = ctx["db"].get(Agent, ctx["agent_id"])
    version = ctx["db"].get(AgentVersion, execution.agent_version_id)

    assert execution.agent_version_id is not None
    assert agent.current_version_id == version.id
    assert version.agent_id == agent.id
    assert version.version_number == 1
    assert version.name == agent.name
    assert version.instructions == agent.instructions
    assert version.runtime == execution.runtime
    assert version.data_class == execution.data_class
    assert len(version.config_sha256) == 64
