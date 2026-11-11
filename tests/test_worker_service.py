
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.execution_service import create_execution
from app.models import (
    Agent,
    AuditEvent,
    DataClass,
    Execution,
    ExecutionAttempt,
    ExecutionAttemptStatus,
    ExecutionStatus,
    Organization,
    Task,
    User,
    Workspace,
)
from app.worker_service import claim_next_execution



import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.execution_service import create_execution
from app.models import (
    Agent,
    AuditEvent,
    DataClass,
    Execution,
    ExecutionAttempt,
    ExecutionAttemptStatus,
    ExecutionStatus,
    Organization,
    Task,
    User,
    Workspace,
)
from app.worker_service import claim_next_execution


@pytest.fixture
def worker_context(tmp_path):
    # Each test gets its own isolated SQLite database.
    test_database = tmp_path / "worker-tests.db"

    test_engine = create_engine(
        f"sqlite:///{test_database}",
        connect_args={"check_same_thread": False},
    )

    TestSessionLocal = sessionmaker(
        bind=test_engine,
        autoflush=False,
        autocommit=False,
    )

    Base.metadata.create_all(bind=test_engine)
    db = TestSessionLocal()

    suffix = uuid.uuid4().hex[:10]

    user = User(
        email=f"worker-{suffix}@test.local",
        display_name="Worker Test",
    )
    org = Organization(name=f"Worker Org {suffix}")

    db.add_all([user, org])
    db.flush()

    workspace = Workspace(
        id=f"worker-ws-{suffix}",
        org_id=org.id,
        name="Worker Workspace",
    )
    db.add(workspace)
    db.flush()

    agent = Agent(
        org_id=org.id,
        workspace_id=workspace.id,
        name="Worker Test Agent",
        runtime="claude_managed_agents",
        data_class=DataClass.synthetic,
        enabled=True,
    )
    task = Task(
        org_id=org.id,
        workspace_id=workspace.id,
        title="Worker Test Task",
        description="Synthetic worker test",
        created_by=user.id,
    )

    db.add_all([agent, task])
    db.commit()

    context = {
        "db": db,
        "org_id": org.id,
        "workspace_id": workspace.id,
        "user_id": user.id,
        "agent_id": agent.id,
        "task_id": task.id,
    }

    try:
        yield context
    finally:
        db.rollback()
        db.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


def create_worker_execution(ctx, **overrides):
    args = {
        "org_id": ctx["org_id"],
        "workspace_id": ctx["workspace_id"],
        "task_id": ctx["task_id"],
        "agent_id": ctx["agent_id"],
        "requested_by": ctx["user_id"],
        "idempotency_key": f"worker-{uuid.uuid4().hex}",
    }
    args.update(overrides)

    return create_execution(ctx["db"], **args)


def test_claim_creates_attempt_and_audit_event(worker_context):
    ctx = worker_context
    db = ctx["db"]

    execution = create_worker_execution(ctx)
    db.commit()

    claimed = claim_next_execution(
        db,
        worker_id="worker-test-1",
        lease_seconds=60,
    )

    assert claimed is not None

    claimed_execution, attempt = claimed

    assert claimed_execution.id == execution.id
    assert claimed_execution.status == ExecutionStatus.claimed
    assert claimed_execution.attempt_count == 1

    assert attempt.execution_id == execution.id
    assert attempt.attempt_number == 1
    assert attempt.worker_id == "worker-test-1"
    assert attempt.runtime == execution.runtime
    assert attempt.status == ExecutionAttemptStatus.claimed
    assert attempt.lease_expires_at is not None
    assert attempt.heartbeat_at is not None

    db.commit()

    event = (
        db.query(AuditEvent)
        .filter_by(
            org_id=ctx["org_id"],
            resource_type="execution",
            resource_id=execution.id,
            event_type="execution.claimed",
        )
        .one()
    )

    assert event.actor_user_id is None
    assert event.workspace_id == ctx["workspace_id"]
    assert event.payload["attempt_id"] == attempt.id
    assert event.payload["attempt_number"] == 1
    assert event.payload["worker_id"] == "worker-test-1"


def test_claim_returns_none_when_no_execution_is_queued(worker_context):
    ctx = worker_context
    db = ctx["db"]

    execution = create_worker_execution(ctx)
    db.commit()

    first_claim = claim_next_execution(
        db,
        worker_id="worker-test-1",
    )
    assert first_claim is not None
    db.commit()

    second_claim = claim_next_execution(
        db,
        worker_id="worker-test-2",
    )

    assert second_claim is None

    db.refresh(execution)
    assert execution.status == ExecutionStatus.claimed
    assert execution.attempt_count == 1


def test_claim_increments_attempt_number_after_retry(worker_context):
    ctx = worker_context
    db = ctx["db"]

    execution = create_worker_execution(ctx, max_attempts=2)
    db.commit()

    first_claim = claim_next_execution(
        db,
        worker_id="worker-test-1",
    )
    assert first_claim is not None

    _, first_attempt = first_claim
    db.commit()

    # Simulate the lifecycle transition after a failed attempt.
    first_attempt.status = ExecutionAttemptStatus.failed
    first_attempt.finished_at = datetime.now(timezone.utc)

    execution.status = ExecutionStatus.queued
    db.commit()

    second_claim = claim_next_execution(
        db,
        worker_id="worker-test-2",
    )

    assert second_claim is not None

    second_execution, second_attempt = second_claim

    assert second_execution.id == execution.id
    assert second_execution.attempt_count == 2
    assert second_attempt.attempt_number == 2
    assert second_attempt.worker_id == "worker-test-2"

    db.commit()

    attempts = (
        db.query(ExecutionAttempt)
        .filter_by(execution_id=execution.id)
        .order_by(ExecutionAttempt.attempt_number.asc())
        .all()
    )

    assert len(attempts) == 2
    assert [attempt.attempt_number for attempt in attempts] == [1, 2]


def test_claim_skips_execution_with_exhausted_attempts(worker_context):
    ctx = worker_context
    db = ctx["db"]

    execution = create_worker_execution(ctx, max_attempts=1)
    db.commit()

    # Simulate an execution that has already consumed its attempt limit.
    execution.attempt_count = execution.max_attempts
    db.commit()

    claimed = claim_next_execution(
        db,
        worker_id="worker-test-1",
    )

    assert claimed is None

    db.refresh(execution)
    assert execution.status == ExecutionStatus.queued
    assert execution.attempt_count == 1


@pytest.mark.parametrize(
    "worker_id, lease_seconds",
    [
        ("", 60),
        ("worker-test", 14),
        ("worker-test", 3601),
    ],
)
def test_claim_rejects_invalid_worker_parameters(
    worker_context,
    worker_id,
    lease_seconds,
):
    with pytest.raises(ValueError):
        claim_next_execution(
            worker_context["db"],
            worker_id=worker_id,
            lease_seconds=lease_seconds,
        )
