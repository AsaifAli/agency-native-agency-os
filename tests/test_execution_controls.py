import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import (
    Agent, AuditEvent, DataClass, Execution, ExecutionStatus,
    Organization, Task, User, Workspace,
)
import app.workforce_models  # noqa: F401 — register worker service metadata
from app.execution_controls import (
    ExecutionNotFound,
    InvalidExecutionState,
    request_execution_cancel,
)


@pytest.fixture
def control_context(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'execution-controls.db'}")
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    db = Session()
    suffix = uuid.uuid4().hex[:12]
    user = User(email=f"control-{suffix}@test.local", display_name="Control Test")
    org = Organization(name=f"Control Org {suffix}")
    db.add_all([user, org])
    db.flush()
    workspace = Workspace(id=f"control-ws-{suffix}", org_id=org.id, name="Control Workspace")
    db.add(workspace)
    db.flush()
    agent = Agent(
        org_id=org.id, workspace_id=workspace.id, name="Control Agent",
        runtime="mock", data_class=DataClass.synthetic, enabled=True,
    )
    task = Task(
        org_id=org.id, workspace_id=workspace.id, title="Control Task",
        description="Synthetic control test", created_by=user.id,
    )
    db.add_all([agent, task])
    db.flush()
    execution = Execution(
        org_id=org.id, workspace_id=workspace.id, task_id=task.id,
        agent_id=agent.id, requested_by=user.id,
        idempotency_key=f"control-{suffix}", runtime="mock",
        data_class=DataClass.synthetic, status=ExecutionStatus.queued,
        request_metadata={},
    )
    db.add(execution)
    db.commit()
    context = {
        "db": db, "org_id": org.id, "workspace_id": workspace.id,
        "user_id": user.id, "execution_id": execution.id,
    }
    try:
        yield context
    finally:
        db.rollback()
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_cancel_queued_execution_is_immediately_terminal_and_audited(control_context):
    ctx = control_context
    execution = request_execution_cancel(
        ctx["db"], execution_id=ctx["execution_id"], org_id=ctx["org_id"],
        workspace_id=ctx["workspace_id"], actor_user_id=ctx["user_id"],
    )
    ctx["db"].commit()

    assert execution.status == ExecutionStatus.cancelled
    assert execution.finished_at is not None
    event = ctx["db"].query(AuditEvent).filter_by(
        org_id=ctx["org_id"], resource_id=ctx["execution_id"],
        event_type="execution.cancelled",
    ).one()
    assert event.actor_user_id == ctx["user_id"]


def test_cancel_running_execution_records_cooperative_request(control_context):
    ctx = control_context
    execution = ctx["db"].get(Execution, ctx["execution_id"])
    execution.status = ExecutionStatus.running
    ctx["db"].commit()

    execution = request_execution_cancel(
        ctx["db"], execution_id=ctx["execution_id"], org_id=ctx["org_id"],
        workspace_id=ctx["workspace_id"], actor_user_id=ctx["user_id"],
    )
    ctx["db"].commit()

    request = execution.request_metadata["control_request"]
    assert request["action"] == "cancel"
    assert request["requested_by"] == ctx["user_id"]
    assert execution.status == ExecutionStatus.running
    assert ctx["db"].query(AuditEvent).filter_by(
        org_id=ctx["org_id"], resource_id=ctx["execution_id"],
        event_type="execution.cancel_requested",
    ).count() == 1


def test_cancel_rejects_execution_outside_requested_workspace(control_context):
    ctx = control_context
    with pytest.raises(ExecutionNotFound):
        request_execution_cancel(
            ctx["db"], execution_id=ctx["execution_id"], org_id=ctx["org_id"],
            workspace_id="another-workspace", actor_user_id=ctx["user_id"],
        )


def test_cancel_rejects_successful_execution(control_context):
    ctx = control_context
    execution = ctx["db"].get(Execution, ctx["execution_id"])
    execution.status = ExecutionStatus.succeeded
    ctx["db"].commit()

    with pytest.raises(InvalidExecutionState):
        request_execution_cancel(
            ctx["db"], execution_id=ctx["execution_id"], org_id=ctx["org_id"],
            workspace_id=ctx["workspace_id"], actor_user_id=ctx["user_id"],
        )
