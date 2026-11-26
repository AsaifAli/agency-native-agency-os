import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import (
    Agent, AuditEvent, DataClass, Execution, ExecutionAttempt, ExecutionAttemptStatus,
    ExecutionStatus, Organization, Task, User, Workspace,
)
from app.execution_controls import (
    ExecutionNotFound,
    InvalidExecutionState,
    request_execution_pause,
    resume_execution,
    acknowledge_execution_pause,
)


@pytest.fixture
def pause_context(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'execution-pause.db'}")
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    db = Session()
    suffix = uuid.uuid4().hex[:12]
    user = User(email=f"pause-{suffix}@test.local", display_name="Pause Test")
    org = Organization(name=f"Pause Org {suffix}")
    db.add_all([user, org])
    db.flush()
    workspace = Workspace(id=f"pause-ws-{suffix}", org_id=org.id, name="Pause Workspace")
    db.add(workspace)
    db.flush()
    agent = Agent(org_id=org.id, workspace_id=workspace.id, name="Pause Agent",
                  runtime="claude_managed_agents", data_class=DataClass.synthetic, enabled=True)
    task = Task(org_id=org.id, workspace_id=workspace.id, title="Pause Task",
                description="Synthetic pause test", created_by=user.id)
    db.add_all([agent, task])
    db.flush()
    execution = Execution(
        org_id=org.id, workspace_id=workspace.id, task_id=task.id, agent_id=agent.id,
        requested_by=user.id, idempotency_key=f"pause-{suffix}",
        runtime="claude_managed_agents", data_class=DataClass.synthetic,
        status=ExecutionStatus.queued, request_metadata={},
    )
    db.add(execution)
    db.commit()
    ctx = {"db": db, "session_factory": Session, "org_id": org.id,
           "workspace_id": workspace.id, "user_id": user.id, "execution_id": execution.id}
    try:
        yield ctx
    finally:
        db.rollback()
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_pause_queued_execution_without_attempts_is_immediate_and_audited(pause_context):
    ctx = pause_context
    execution = request_execution_pause(
        ctx["db"], execution_id=ctx["execution_id"], org_id=ctx["org_id"],
        workspace_id=ctx["workspace_id"], actor_user_id=ctx["user_id"],
    )
    ctx["db"].commit()
    assert execution.status == ExecutionStatus.paused
    assert execution.finished_at is None
    assert ctx["db"].query(AuditEvent).filter_by(
        resource_id=ctx["execution_id"], event_type="execution.paused"
    ).count() == 1


def test_pause_active_execution_persists_request_until_worker_acknowledges(pause_context):
    ctx = pause_context
    execution = ctx["db"].get(Execution, ctx["execution_id"])
    execution.status = ExecutionStatus.running
    attempt = ExecutionAttempt(
        execution_id=execution.id, attempt_number=1, worker_id="pause-worker",
        runtime=execution.runtime, status=ExecutionAttemptStatus.running,
        lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    ctx["db"].add(attempt)
    ctx["db"].commit()
    attempt_id = attempt.id

    execution = request_execution_pause(
        ctx["db"], execution_id=ctx["execution_id"], org_id=ctx["org_id"],
        workspace_id=ctx["workspace_id"], actor_user_id=ctx["user_id"],
    )
    ctx["db"].commit()
    assert execution.status == ExecutionStatus.running
    assert execution.request_metadata["control_request"]["action"] == "pause"

    with ctx["session_factory"]() as worker_db:
        acknowledged, saved_attempt = acknowledge_execution_pause(
            worker_db, execution_id=execution.id, attempt_id=attempt_id,
            worker_id="pause-worker",
        )
        worker_db.commit()
        assert acknowledged.status == ExecutionStatus.paused
        assert saved_attempt.status == ExecutionAttemptStatus.paused
        assert saved_attempt.lease_expires_at is None


def test_resume_paused_execution_queues_same_provider_session_and_rotates_token(pause_context):
    ctx = pause_context
    execution = ctx["db"].get(Execution, ctx["execution_id"])
    execution.status = ExecutionStatus.paused
    execution.request_metadata = {
        "control_request": {"action": "pause", "requested_by": ctx["user_id"]},
    }
    attempt = ExecutionAttempt(
        execution_id=execution.id, attempt_number=1, worker_id="old-worker",
        runtime=execution.runtime, status=ExecutionAttemptStatus.paused,
        external_run_id="sesn_existing",
    )
    ctx["db"].add(attempt)
    ctx["db"].commit()

    resumed = resume_execution(
        ctx["db"], execution_id=execution.id, org_id=ctx["org_id"],
        workspace_id=ctx["workspace_id"], actor_user_id=ctx["user_id"],
    )
    ctx["db"].commit()
    control = resumed.request_metadata["control_request"]
    assert resumed.status == ExecutionStatus.queued
    assert control["action"] == "resume"
    assert control["resume_token"]
    assert control["resume_event_id"] is None
    saved_attempt = ctx["db"].query(ExecutionAttempt).filter_by(execution_id=execution.id).one()
    assert saved_attempt.external_run_id == "sesn_existing"


def test_resume_rejects_non_paused_execution(pause_context):
    ctx = pause_context
    with pytest.raises(InvalidExecutionState):
        resume_execution(
            ctx["db"], execution_id=ctx["execution_id"], org_id=ctx["org_id"],
            workspace_id=ctx["workspace_id"], actor_user_id=ctx["user_id"],
        )


def test_pause_rejects_execution_outside_requested_workspace(pause_context):
    ctx = pause_context
    with pytest.raises(ExecutionNotFound):
        request_execution_pause(
            ctx["db"], execution_id=ctx["execution_id"], org_id=ctx["org_id"],
            workspace_id="other-workspace", actor_user_id=ctx["user_id"],
        )



def test_pause_rejects_active_runtime_without_safe_interrupt_support(pause_context):
    ctx = pause_context
    execution = ctx["db"].get(Execution, ctx["execution_id"])
    execution.runtime = "mock"
    execution.status = ExecutionStatus.running
    ctx["db"].commit()
    with pytest.raises(InvalidExecutionState, match="cannot safely pause"):
        request_execution_pause(
            ctx["db"], execution_id=execution.id, org_id=ctx["org_id"],
            workspace_id=ctx["workspace_id"], actor_user_id=ctx["user_id"],
        )
