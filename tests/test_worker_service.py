import uuid
from datetime import datetime, timedelta, timezone

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
from app.worker_service import (
    InvalidExecutionState,
    LeaseExpired,
    WorkerOwnershipError,
    claim_next_execution,
    complete_execution,
    fail_execution,
    heartbeat_execution,
    promote_due_retries,
    recover_expired_execution_leases,
    start_execution,
)


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

def claim_for_lifecycle_test(ctx, worker_id="worker-lifecycle-1"):
    execution = create_worker_execution(ctx)
    ctx["db"].commit()

    claimed = claim_next_execution(
        ctx["db"],
        worker_id=worker_id,
        lease_seconds=60,
    )
    assert claimed is not None

    ctx["db"].commit()
    return claimed


def test_start_execution_transitions_claimed_to_running(worker_context):
    ctx = worker_context
    db = ctx["db"]

    execution, attempt = claim_for_lifecycle_test(ctx)

    started_execution, started_attempt = start_execution(
        db,
        execution_id=execution.id,
        attempt_id=attempt.id,
        worker_id="worker-lifecycle-1",
        lease_seconds=120,
    )

    assert started_execution.status == ExecutionStatus.running
    assert started_execution.started_at is not None
    assert started_attempt.status == ExecutionAttemptStatus.running
    assert started_attempt.started_at is not None
    assert started_attempt.heartbeat_at is not None
    assert started_attempt.lease_expires_at is not None
    assert started_execution.last_attempt_at is not None

    db.commit()

    event = db.query(AuditEvent).filter_by(
        resource_id=execution.id,
        event_type="execution.started",
    ).one()

    assert event.payload["attempt_id"] == attempt.id
    assert event.payload["worker_id"] == "worker-lifecycle-1"


def test_heartbeat_execution_renews_active_lease(worker_context):
    ctx = worker_context
    db = ctx["db"]

    execution, attempt = claim_for_lifecycle_test(ctx)

    start_execution(
        db,
        execution_id=execution.id,
        attempt_id=attempt.id,
        worker_id="worker-lifecycle-1",
    )
    db.commit()

    old_lease = attempt.lease_expires_at

    _, renewed_attempt = heartbeat_execution(
        db,
        execution_id=execution.id,
        attempt_id=attempt.id,
        worker_id="worker-lifecycle-1",
        lease_seconds=180,
    )

    assert renewed_attempt.heartbeat_at is not None
    assert renewed_attempt.lease_expires_at is not None

    old_lease_utc = (
        old_lease.replace(tzinfo=timezone.utc)
        if old_lease.tzinfo is None
        else old_lease.astimezone(timezone.utc)
    )
    renewed_lease_utc = (
        renewed_attempt.lease_expires_at.replace(tzinfo=timezone.utc)
        if renewed_attempt.lease_expires_at.tzinfo is None
        else renewed_attempt.lease_expires_at.astimezone(timezone.utc)
    )

    assert renewed_lease_utc > old_lease_utc

    db.commit()


def test_complete_execution_persists_result_and_audit_event(worker_context):
    ctx = worker_context
    db = ctx["db"]

    execution, attempt = claim_for_lifecycle_test(ctx)

    start_execution(
        db,
        execution_id=execution.id,
        attempt_id=attempt.id,
        worker_id="worker-lifecycle-1",
    )
    db.commit()

    result = {
        "status": "completed",
        "summary": "Synthetic test result",
    }

    completed_execution, completed_attempt = complete_execution(
        db,
        execution_id=execution.id,
        attempt_id=attempt.id,
        worker_id="worker-lifecycle-1",
        result=result,
    )

    assert completed_execution.status == ExecutionStatus.succeeded
    assert completed_execution.result == result
    assert completed_execution.finished_at is not None

    assert completed_attempt.status == ExecutionAttemptStatus.succeeded
    assert completed_attempt.result == result
    assert completed_attempt.finished_at is not None
    assert completed_attempt.lease_expires_at is None

    db.commit()

    event = db.query(AuditEvent).filter_by(
        resource_id=execution.id,
        event_type="execution.succeeded",
    ).one()

    assert event.payload["attempt_id"] == attempt.id


def test_worker_cannot_start_another_workers_attempt(worker_context):
    ctx = worker_context
    execution, attempt = claim_for_lifecycle_test(ctx)

    with pytest.raises(WorkerOwnershipError):
        start_execution(
            ctx["db"],
            execution_id=execution.id,
            attempt_id=attempt.id,
            worker_id="different-worker",
        )


def test_worker_cannot_heartbeat_expired_lease(worker_context):
    ctx = worker_context
    db = ctx["db"]

    execution, attempt = claim_for_lifecycle_test(ctx)

    attempt.lease_expires_at = datetime.now(timezone.utc) - timedelta(
        seconds=30
    )
    db.commit()

    with pytest.raises(LeaseExpired):
        heartbeat_execution(
            db,
            execution_id=execution.id,
            attempt_id=attempt.id,
            worker_id="worker-lifecycle-1",
        )


def test_start_execution_rejects_already_running_execution(worker_context):
    ctx = worker_context
    db = ctx["db"]

    execution, attempt = claim_for_lifecycle_test(ctx)

    start_execution(
        db,
        execution_id=execution.id,
        attempt_id=attempt.id,
        worker_id="worker-lifecycle-1",
    )
    db.commit()

    with pytest.raises(InvalidExecutionState):
        start_execution(
            db,
            execution_id=execution.id,
            attempt_id=attempt.id,
            worker_id="worker-lifecycle-1",
        )


def test_complete_execution_rejects_non_dictionary_result(worker_context):
    ctx = worker_context
    db = ctx["db"]

    execution, attempt = claim_for_lifecycle_test(ctx)

    start_execution(
        db,
        execution_id=execution.id,
        attempt_id=attempt.id,
        worker_id="worker-lifecycle-1",
    )
    db.commit()

    with pytest.raises(ValueError, match="result must be a dictionary"):
        complete_execution(
            db,
            execution_id=execution.id,
            attempt_id=attempt.id,
            worker_id="worker-lifecycle-1",
            result=["not", "a", "dictionary"],
        )


def start_running_attempt(
    ctx,
    *,
    max_attempts=3,
    worker_id="worker-retry-test",
):
    """Create an execution, claim it and start its first attempt."""
    db = ctx["db"]

    execution = create_worker_execution(
        ctx,
        max_attempts=max_attempts,
    )
    db.commit()

    claimed = claim_next_execution(
        db,
        worker_id=worker_id,
        lease_seconds=120,
    )
    assert claimed is not None

    execution, attempt = claimed
    db.commit()

    execution, attempt = start_execution(
        db,
        execution_id=execution.id,
        attempt_id=attempt.id,
        worker_id=worker_id,
        lease_seconds=120,
    )
    db.commit()

    return execution, attempt, worker_id


def utc_datetime(value):
    """Normalize SQLite and PostgreSQL datetime values for assertions."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def test_retryable_failure_schedules_retry(worker_context):
    ctx = worker_context
    db = ctx["db"]

    execution, attempt, worker_id = start_running_attempt(ctx)

    failed_execution, failed_attempt = fail_execution(
        db,
        execution_id=execution.id,
        attempt_id=attempt.id,
        worker_id=worker_id,
        error_code="TEMPORARY_ERROR",
        error_message="Synthetic temporary failure",
        retryable=True,
        base_delay_seconds=10,
        max_delay_seconds=100,
    )

    assert failed_execution.status == ExecutionStatus.retry_wait
    assert failed_execution.finished_at is None
    assert failed_execution.next_retry_at is not None
    assert failed_execution.error_code == "TEMPORARY_ERROR"
    assert failed_execution.last_attempt_at is not None

    assert failed_attempt.status == ExecutionAttemptStatus.failed
    assert failed_attempt.finished_at is not None
    assert failed_attempt.lease_expires_at is None

    actual_delay = (
        utc_datetime(failed_execution.next_retry_at)
        - utc_datetime(failed_attempt.finished_at)
    ).total_seconds()

    assert 9 <= actual_delay <= 11

    db.commit()

    retry_event = db.query(AuditEvent).filter_by(
        resource_id=execution.id,
        event_type="execution.retry_scheduled",
    ).one()

    attempt_event = db.query(AuditEvent).filter_by(
        resource_id=attempt.id,
        event_type="execution.attempt_failed",
    ).one()

    assert retry_event.payload["error_code"] == "TEMPORARY_ERROR"
    assert retry_event.payload["retry_delay_seconds"] == 10
    assert attempt_event.payload["attempt_number"] == 1


def test_non_retryable_failure_is_terminal(worker_context):
    ctx = worker_context
    db = ctx["db"]

    execution, attempt, worker_id = start_running_attempt(ctx)

    failed_execution, failed_attempt = fail_execution(
        db,
        execution_id=execution.id,
        attempt_id=attempt.id,
        worker_id=worker_id,
        error_code="PERMANENT_ERROR",
        error_message="Synthetic permanent failure",
        retryable=False,
    )

    assert failed_execution.status == ExecutionStatus.failed
    assert failed_execution.finished_at is not None
    assert failed_execution.next_retry_at is None

    assert failed_attempt.status == ExecutionAttemptStatus.failed
    assert failed_attempt.lease_expires_at is None

    db.commit()

    event = db.query(AuditEvent).filter_by(
        resource_id=execution.id,
        event_type="execution.failed",
    ).one()

    assert event.payload["retryable"] is False


def test_exhausted_attempts_produce_terminal_failure(worker_context):
    ctx = worker_context
    db = ctx["db"]

    execution, attempt, worker_id = start_running_attempt(
        ctx,
        max_attempts=1,
    )

    failed_execution, _ = fail_execution(
        db,
        execution_id=execution.id,
        attempt_id=attempt.id,
        worker_id=worker_id,
        error_code="ATTEMPT_LIMIT",
        error_message="Attempt limit reached",
        retryable=True,
        base_delay_seconds=10,
    )

    assert failed_execution.attempt_count == 1
    assert failed_execution.max_attempts == 1
    assert failed_execution.status == ExecutionStatus.failed
    assert failed_execution.finished_at is not None
    assert failed_execution.next_retry_at is None


def test_second_attempt_uses_exponential_backoff(worker_context):
    ctx = worker_context
    db = ctx["db"]

    execution, first_attempt, worker_id = start_running_attempt(
        ctx,
        max_attempts=3,
    )

    fail_execution(
        db,
        execution_id=execution.id,
        attempt_id=first_attempt.id,
        worker_id=worker_id,
        error_code="TEMPORARY_ERROR",
        error_message="First failure",
        retryable=True,
        base_delay_seconds=10,
        max_delay_seconds=100,
    )
    db.commit()

    # Make the scheduled retry due.
    execution.next_retry_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()

    assert promote_due_retries(db) == 1
    db.commit()

    second_claim = claim_next_execution(
        db,
        worker_id="worker-retry-second",
        lease_seconds=120,
    )
    assert second_claim is not None

    execution, second_attempt = second_claim
    db.commit()

    start_execution(
        db,
        execution_id=execution.id,
        attempt_id=second_attempt.id,
        worker_id="worker-retry-second",
        lease_seconds=120,
    )
    db.commit()

    failed_execution, failed_attempt = fail_execution(
        db,
        execution_id=execution.id,
        attempt_id=second_attempt.id,
        worker_id="worker-retry-second",
        error_code="TEMPORARY_ERROR",
        error_message="Second failure",
        retryable=True,
        base_delay_seconds=10,
        max_delay_seconds=100,
    )

    assert failed_execution.attempt_count == 2
    assert failed_execution.status == ExecutionStatus.retry_wait

    actual_delay = (
        utc_datetime(failed_execution.next_retry_at)
        - utc_datetime(failed_attempt.finished_at)
    ).total_seconds()

    assert 19 <= actual_delay <= 21


def test_promote_due_retries_queues_only_due_executions(worker_context):
    ctx = worker_context
    db = ctx["db"]

    due_execution, due_attempt, worker_id = start_running_attempt(ctx)
    future_execution, future_attempt, future_worker = start_running_attempt(ctx)

    fail_execution(
        db,
        execution_id=due_execution.id,
        attempt_id=due_attempt.id,
        worker_id=worker_id,
        error_code="TEMPORARY_ERROR",
        error_message="Due retry",
        retryable=True,
        base_delay_seconds=10,
    )

    fail_execution(
        db,
        execution_id=future_execution.id,
        attempt_id=future_attempt.id,
        worker_id=future_worker,
        error_code="TEMPORARY_ERROR",
        error_message="Future retry",
        retryable=True,
        base_delay_seconds=3600,
    )
    db.commit()

    due_execution.next_retry_at = datetime.now(timezone.utc) - timedelta(
        seconds=1
    )
    db.commit()

    promoted_count = promote_due_retries(db, limit=100)

    assert promoted_count == 1
    assert due_execution.status == ExecutionStatus.queued
    assert due_execution.next_retry_at is None

    assert future_execution.status == ExecutionStatus.retry_wait
    assert future_execution.next_retry_at is not None


def test_promote_due_retries_respects_limit(worker_context):
    ctx = worker_context
    db = ctx["db"]

    executions = []

    for _ in range(2):
        execution, attempt, worker_id = start_running_attempt(ctx)

        fail_execution(
            db,
            execution_id=execution.id,
            attempt_id=attempt.id,
            worker_id=worker_id,
            error_code="TEMPORARY_ERROR",
            error_message="Due retry",
            retryable=True,
            base_delay_seconds=10,
        )

        execution.next_retry_at = datetime.now(timezone.utc) - timedelta(
            seconds=1
        )
        executions.append(execution)

    db.commit()

    promoted_count = promote_due_retries(db, limit=1)

    assert promoted_count == 1
    assert sum(
        item.status == ExecutionStatus.queued for item in executions
    ) == 1
    assert sum(
        item.status == ExecutionStatus.retry_wait for item in executions
    ) == 1

def test_recovery_abandons_expired_claimed_attempt(worker_context):
    ctx = worker_context
    db = ctx["db"]

    execution = create_worker_execution(ctx)
    db.commit()

    claimed = claim_next_execution(
        db,
        worker_id="worker-expired-claimed",
        lease_seconds=60,
    )
    assert claimed is not None

    execution, attempt = claimed
    attempt.lease_expires_at = datetime.now(timezone.utc) - timedelta(
        seconds=5
    )
    db.commit()

    recovered = recover_expired_execution_leases(
        db,
        base_delay_seconds=5,
        max_delay_seconds=30,
    )

    assert recovered == 1
    assert execution.status == ExecutionStatus.retry_wait
    assert attempt.status == ExecutionAttemptStatus.abandoned
    assert attempt.lease_expires_at is None
    assert attempt.error_code == "WORKER_LEASE_EXPIRED"
    assert execution.next_retry_at is not None

    db.commit()

    abandoned_event = (
        db.query(AuditEvent)
        .filter_by(
            org_id=ctx["org_id"],
            event_type="execution.attempt_abandoned",
            resource_type="execution_attempt",
            resource_id=attempt.id,
        )
        .one()
    )

    assert abandoned_event.payload["worker_id"] == "worker-expired-claimed"


def test_recovery_abandons_expired_running_attempt(worker_context):
    ctx = worker_context
    db = ctx["db"]

    execution, attempt, worker_id = start_running_attempt(ctx)

    attempt.lease_expires_at = datetime.now(timezone.utc) - timedelta(
        seconds=5
    )
    db.commit()

    recovered = recover_expired_execution_leases(
        db,
        base_delay_seconds=5,
        max_delay_seconds=30,
    )

    assert recovered == 1
    assert execution.status == ExecutionStatus.retry_wait
    assert attempt.status == ExecutionAttemptStatus.abandoned
    assert execution.error_code == "WORKER_LEASE_EXPIRED"
    assert execution.finished_at is None
    assert execution.next_retry_at is not None

    db.commit()

    retry_event = (
        db.query(AuditEvent)
        .filter_by(
            org_id=ctx["org_id"],
            event_type="execution.retry_scheduled",
            resource_type="execution",
            resource_id=execution.id,
        )
        .one()
    )

    assert retry_event.payload["recovery_reason"] == "expired_worker_lease"
    assert retry_event.payload["worker_id"] == worker_id


def test_recovery_fails_execution_when_attempts_exhausted(worker_context):
    ctx = worker_context
    db = ctx["db"]

    execution, attempt, _ = start_running_attempt(
        ctx,
        max_attempts=1,
    )

    attempt.lease_expires_at = datetime.now(timezone.utc) - timedelta(
        seconds=5
    )
    db.commit()

    recovered = recover_expired_execution_leases(db)

    assert recovered == 1
    assert execution.status == ExecutionStatus.failed
    assert execution.attempt_count == execution.max_attempts == 1
    assert execution.finished_at is not None
    assert execution.next_retry_at is None
    assert attempt.status == ExecutionAttemptStatus.abandoned
    assert attempt.error_code == "WORKER_LEASE_EXPIRED"

    db.commit()

    failed_event = (
        db.query(AuditEvent)
        .filter_by(
            org_id=ctx["org_id"],
            event_type="execution.failed",
            resource_type="execution",
            resource_id=execution.id,
        )
        .one()
    )

    assert failed_event.payload["attempts_exhausted"] is True
    assert failed_event.payload["recovery_reason"] == "expired_worker_lease"


def test_recovery_ignores_unexpired_worker_lease(worker_context):
    ctx = worker_context
    db = ctx["db"]

    execution = create_worker_execution(ctx)
    db.commit()

    claimed = claim_next_execution(
        db,
        worker_id="worker-active-lease",
        lease_seconds=120,
    )
    assert claimed is not None

    execution, attempt = claimed
    db.commit()

    recovered = recover_expired_execution_leases(db)

    assert recovered == 0
    assert execution.status == ExecutionStatus.claimed
    assert attempt.status == ExecutionAttemptStatus.claimed
    assert attempt.lease_expires_at is not None


def test_recovery_respects_limit(worker_context):
    ctx = worker_context
    db = ctx["db"]

    expired_attempts = []

    for _ in range(2):
        execution, attempt, _ = start_running_attempt(ctx)

        attempt.lease_expires_at = datetime.now(timezone.utc) - timedelta(
            seconds=5
        )
        expired_attempts.append((execution, attempt))

    db.commit()

    recovered = recover_expired_execution_leases(
        db,
        limit=1,
    )

    assert recovered == 1

    abandoned_count = sum(
        attempt.status == ExecutionAttemptStatus.abandoned
        for _, attempt in expired_attempts
    )
    running_count = sum(
        execution.status == ExecutionStatus.running
        for execution, _ in expired_attempts
    )

    assert abandoned_count == 1
    assert running_count == 1