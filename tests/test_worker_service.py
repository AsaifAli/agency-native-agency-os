import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.config import settings
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
    queue_ready_delegations,
    _aggregate_provider_usage,
)

import time
from threading import Event

from app.integrations.runtime import ExecutionResult
from app.worker import processor as processor_module
from app.worker.processor import LeaseHeartbeat, process_one_execution, HeartbeatRenewalError


@pytest.fixture
def worker_context(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(settings, "mock_runtime_enabled", True)
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
        runtime="mock",
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


def mock_worker_context(ctx):
    """Create a valid execution, then route it to the local mock runtime."""
    execution = create_worker_execution(ctx)

    session_factory = sessionmaker(
        bind=ctx["db"].get_bind(),
        autoflush=False,
        autocommit=False,
    )

    return execution, session_factory


def test_processor_completes_mock_execution(worker_context):
    ctx = worker_context
    execution, session_factory = mock_worker_context(ctx)

    processed_id = process_one_execution(
        worker_id="processor-test-1",
        session_factory=session_factory,
    )

    assert processed_id == execution.id

    ctx["db"].expire_all()
    saved_execution = ctx["db"].get(Execution, execution.id)

    assert saved_execution.status == ExecutionStatus.succeeded
    assert saved_execution.result["provider"] == "mock"
    assert saved_execution.result["status"] == "succeeded"

    attempt = (
        ctx["db"].query(ExecutionAttempt)
        .filter_by(execution_id=execution.id)
        .one()
    )
    assert attempt.status == ExecutionAttemptStatus.succeeded
    assert attempt.lease_expires_at is None


def test_processor_rejects_unsupported_runtime(worker_context):
    ctx = worker_context
    execution = create_worker_execution(ctx)
    execution.runtime = "unsupported_runtime"
    ctx["db"].commit()

    session_factory = sessionmaker(
        bind=ctx["db"].get_bind(),
        autoflush=False,
        autocommit=False,
    )

    processed_id = process_one_execution(
        worker_id="processor-test-2",
        session_factory=session_factory,
    )

    assert processed_id == execution.id

    ctx["db"].expire_all()
    saved_execution = ctx["db"].get(Execution, execution.id)

    assert saved_execution.status == ExecutionStatus.failed
    assert saved_execution.error_code == "RUNTIME_NOT_CONFIGURED"

    attempt = (
        ctx["db"].query(ExecutionAttempt)
        .filter_by(execution_id=execution.id)
        .one()
    )
    assert attempt.status == ExecutionAttemptStatus.failed


def test_processor_blocks_secret_input_and_persists_only_reason_code(worker_context, monkeypatch):
    ctx = worker_context
    task = ctx["db"].get(Task, ctx["task_id"])
    task.description = "Use this credential sk-ant-api-1234567890abcdefghijkl"
    execution = create_worker_execution(ctx)
    ctx["db"].commit()

    monkeypatch.setattr(
        "app.worker.processor.get_runtime",
        lambda _: pytest.fail("provider must not be called for blocked input"),
    )
    session_factory = sessionmaker(
        bind=ctx["db"].get_bind(), autoflush=False, autocommit=False,
    )
    processed_id = process_one_execution(
        worker_id="dpg-input-block", session_factory=session_factory,
    )
    assert processed_id == execution.id

    ctx["db"].expire_all()
    saved = ctx["db"].get(Execution, execution.id)
    assert saved.status == ExecutionStatus.failed
    assert saved.error_code == "DATA_PROTECTION_BLOCKED"
    event = ctx["db"].query(AuditEvent).filter_by(
        org_id=ctx["org_id"],
        event_type="execution.data_protection_blocked",
        resource_type="execution",
        resource_id=execution.id,
    ).one()
    assert event.payload == {"reason_code": "SECRET_DETECTED"}
    assert "sk-ant" not in str(event.payload)


def test_processor_redacts_provider_output_and_audits_counts(worker_context, monkeypatch):
    ctx = worker_context
    execution = create_worker_execution(ctx)
    ctx["db"].commit()

    class PersonalDataRuntime:
        def start(self, request):
            return ExecutionResult(
                provider="mock", external_run_id="provider-run-456",
                status="succeeded", detail="Contact billing@example.com",
            )

    monkeypatch.setattr(
        "app.worker.processor.get_runtime",
        lambda _: PersonalDataRuntime(),
    )
    session_factory = sessionmaker(
        bind=ctx["db"].get_bind(), autoflush=False, autocommit=False,
    )
    process_one_execution(worker_id="dpg-output-redact", session_factory=session_factory)

    ctx["db"].expire_all()
    saved = ctx["db"].get(Execution, execution.id)
    assert saved.status == ExecutionStatus.succeeded
    assert "billing@example.com" not in saved.result["detail"]
    assert "[REDACTED_EMAIL]" in saved.result["detail"]
    event = ctx["db"].query(AuditEvent).filter_by(
        org_id=ctx["org_id"],
        event_type="execution.output_redacted",
        resource_type="execution",
        resource_id=execution.id,
    ).one()
    assert event.payload["redaction_counts"] == {"EMAIL": 1}


def test_processor_blocks_provider_secret_output_before_result_persistence(worker_context, monkeypatch):
    ctx = worker_context
    execution = create_worker_execution(ctx)
    ctx["db"].commit()

    class SecretOutputRuntime:
        def start(self, request):
            return ExecutionResult(
                provider="mock", external_run_id="provider-run-789",
                status="succeeded", detail="token=sk-ant-api-1234567890abcdefghijkl",
            )

    monkeypatch.setattr(
        "app.worker.processor.get_runtime",
        lambda _: SecretOutputRuntime(),
    )
    session_factory = sessionmaker(
        bind=ctx["db"].get_bind(), autoflush=False, autocommit=False,
    )
    process_one_execution(worker_id="dpg-output-block", session_factory=session_factory)

    ctx["db"].expire_all()
    saved = ctx["db"].get(Execution, execution.id)
    assert saved.status == ExecutionStatus.failed
    assert saved.error_code == "DATA_PROTECTION_BLOCKED"
    assert saved.result is None
    event = ctx["db"].query(AuditEvent).filter_by(
        org_id=ctx["org_id"],
        event_type="execution.output_protection_blocked",
        resource_type="execution",
        resource_id=execution.id,
    ).one()
    assert event.payload == {"reason_code": "SECRET_DETECTED"}


def test_processor_sanitizes_runtime_failure(worker_context, monkeypatch):
    ctx = worker_context
    execution, session_factory = mock_worker_context(ctx)

    class BrokenRuntime:
        def start(self, request):
            raise RuntimeError("provider token=must-not-be-persisted")

    monkeypatch.setattr(
        "app.worker.processor.get_runtime",
        lambda runtime_name: BrokenRuntime(),
    )

    processed_id = process_one_execution(
        worker_id="processor-test-3",
        session_factory=session_factory,
    )

    assert processed_id == execution.id

    ctx["db"].expire_all()
    saved_execution = ctx["db"].get(Execution, execution.id)

    assert saved_execution.status == ExecutionStatus.retry_wait
    assert saved_execution.error_code == "RUNTIME_ERROR"
    assert saved_execution.error_message == (
        "The runtime encountered an execution error."
    )
    assert "must-not-be-persisted" not in saved_execution.error_message

    attempt = (
        ctx["db"].query(ExecutionAttempt)
        .filter_by(execution_id=execution.id)
        .one()
    )
    assert attempt.status == ExecutionAttemptStatus.failed


def test_processor_returns_none_when_queue_is_empty(worker_context):
    ctx = worker_context

    session_factory = sessionmaker(
        bind=ctx["db"].get_bind(),
        autoflush=False,
        autocommit=False,
    )

    result = process_one_execution(
        worker_id="processor-test-4",
        session_factory=session_factory,
    )

    assert result is None

    assert (
        ctx["db"].query(ExecutionAttempt).count()
        == 0
    )

def test_lease_heartbeat_renews_active_attempt(worker_context):
    ctx = worker_context
    execution = create_worker_execution(ctx)
    ctx["db"].commit()

    session_factory = sessionmaker(
        bind=ctx["db"].get_bind(),
        autoflush=False,
        autocommit=False,
    )

    with session_factory() as db:
        claimed = claim_next_execution(
            db,
            worker_id="heartbeat-test",
            lease_seconds=15,
        )
        assert claimed is not None
        _, attempt = claimed
        execution_id = execution.id
        attempt_id = attempt.id
        db.commit()

    with session_factory() as db:
        start_execution(
            db,
            execution_id=execution_id,
            attempt_id=attempt_id,
            worker_id="heartbeat-test",
            lease_seconds=15,
        )
        db.commit()

    with session_factory() as db:
        original_attempt = db.get(ExecutionAttempt, attempt_id)
        original_lease = original_attempt.lease_expires_at

    heartbeat = LeaseHeartbeat(
        session_factory=session_factory,
        execution_id=execution_id,
        attempt_id=attempt_id,
        worker_id="heartbeat-test",
        lease_seconds=15,
        interval_seconds=0.02,
    )

    heartbeat.start()
    time.sleep(0.10)
    heartbeat.stop()
    heartbeat.assert_healthy()

    with session_factory() as db:
        renewed_attempt = db.get(ExecutionAttempt, attempt_id)

        assert renewed_attempt.lease_expires_at > original_lease

@pytest.mark.parametrize("runtime_raises", [False, True])
def test_processor_does_not_persist_after_heartbeat_failure(
    worker_context,
    monkeypatch,
    runtime_raises,
):
    ctx = worker_context
    execution, session_factory = mock_worker_context(ctx)

    heartbeat_failed = Event()

    def failing_heartbeat(*args, **kwargs):
        heartbeat_failed.set()
        raise LeaseExpired("Simulated heartbeat failure")

    monkeypatch.setattr(
        processor_module,
        "heartbeat_execution",
        failing_heartbeat,
    )

    class WaitingRuntime:
        def start(self, request):
            assert heartbeat_failed.wait(timeout=2)

            if runtime_raises:
                raise RuntimeError("Simulated runtime failure")

            return ExecutionResult(
                provider="mock",
                external_run_id="mock-heartbeat-test",
                status="succeeded",
                detail="Test result",
            )

    monkeypatch.setattr(
        processor_module,
        "get_runtime",
        lambda runtime_name: WaitingRuntime(),
    )

    with pytest.raises(LeaseExpired):
        process_one_execution(
            worker_id="heartbeat-failure-test",
            session_factory=session_factory,
            heartbeat_interval_seconds=0.01,
        )

    ctx["db"].expire_all()
    saved_execution = ctx["db"].get(Execution, execution.id)

    assert saved_execution.status == ExecutionStatus.running
    assert saved_execution.result is None
    assert saved_execution.error_code is None

    attempt = (
        ctx["db"].query(ExecutionAttempt)
        .filter_by(execution_id=execution.id)
        .one()
    )

    assert attempt.status == ExecutionAttemptStatus.running

@pytest.mark.parametrize(
    "status",
    ["failed", "cancelled", "not_configured"],
)
def test_processor_classifies_unsuccessful_runtime_status(
    worker_context,
    monkeypatch,
    status,
):
    ctx = worker_context
    execution, session_factory = mock_worker_context(ctx)

    class UnsuccessfulRuntime:
        def start(self, request):
            return ExecutionResult(
                provider="mock",
                external_run_id="mock-unsuccessful",
                status=status,
                detail="Runtime did not succeed.",
            )

    monkeypatch.setattr(
        processor_module,
        "get_runtime",
        lambda runtime_name: UnsuccessfulRuntime(),
    )

    processed_id = process_one_execution(
        worker_id="processor-unsuccessful-test",
        session_factory=session_factory,
    )

    assert processed_id == execution.id

    ctx["db"].expire_all()
    saved = ctx["db"].get(Execution, execution.id)

    assert saved.status == ExecutionStatus.retry_wait
    assert saved.error_code == "RUNTIME_UNSUCCESSFUL"


def test_processor_rejects_invalid_runtime_result(
    worker_context,
    monkeypatch,
):
    ctx = worker_context
    execution, session_factory = mock_worker_context(ctx)

    class InvalidRuntime:
        def start(self, request):
            return ExecutionResult(
                provider="",
                external_run_id=None,
                status="succeeded",
                detail="Invalid provider.",
            )

    monkeypatch.setattr(
        processor_module,
        "get_runtime",
        lambda runtime_name: InvalidRuntime(),
    )

    processed_id = process_one_execution(
        worker_id="processor-invalid-result-test",
        session_factory=session_factory,
    )

    assert processed_id == execution.id

    ctx["db"].expire_all()
    saved = ctx["db"].get(Execution, execution.id)

    assert saved.status == ExecutionStatus.retry_wait
    assert saved.error_code == "RUNTIME_ERROR"

def test_processor_does_not_persist_after_heartbeat_infrastructure_failure(
    worker_context,
    monkeypatch,
):
    ctx = worker_context
    execution, session_factory = mock_worker_context(ctx)

    heartbeat_failed = Event()

    def failing_heartbeat(*args, **kwargs):
        heartbeat_failed.set()
        raise RuntimeError("Database connection unavailable")

    monkeypatch.setattr(
        processor_module,
        "heartbeat_execution",
        failing_heartbeat,
    )

    class WaitingRuntime:
        def start(self, request):
            assert heartbeat_failed.wait(timeout=2)
            return ExecutionResult(
                provider="mock",
                external_run_id="mock-infrastructure-failure",
                status="succeeded",
                detail="Test result",
            )

    monkeypatch.setattr(
        processor_module,
        "get_runtime",
        lambda runtime_name: WaitingRuntime(),
    )

    with pytest.raises(HeartbeatRenewalError):
        process_one_execution(
            worker_id="heartbeat-infrastructure-test",
            session_factory=session_factory,
            heartbeat_interval_seconds=0.01,
        )

    ctx["db"].expire_all()
    saved = ctx["db"].get(Execution, execution.id)

    assert saved.status == ExecutionStatus.running
    assert saved.result is None
    assert saved.error_code is None

    attempt = (
        ctx["db"].query(ExecutionAttempt)
        .filter_by(execution_id=execution.id)
        .one()
    )
    assert attempt.status == ExecutionAttemptStatus.running

@pytest.mark.parametrize(
    "result",
    [
        ExecutionResult(
            provider="p" * 81,
            external_run_id=None,
            status="succeeded",
        ),
        ExecutionResult(
            provider="mock",
            external_run_id="r" * 201,
            status="succeeded",
        ),
        ExecutionResult(
            provider="mock",
            external_run_id=None,
            status="succeeded",
            detail="d" * 16001,
        ),
        ExecutionResult(
            provider="",
            external_run_id=None,
            status="succeeded",
        ),
        ExecutionResult(
            provider="mock",
            external_run_id="",
            status="succeeded",
        ),
    ],
)
def test_runtime_result_rejects_invalid_or_oversized_fields(result):
    with pytest.raises(ValueError):
        processor_module._serialize_result(result)


def test_runtime_result_rejects_non_string_detail():
    result = ExecutionResult(
        provider="mock",
        external_run_id=None,
        status="succeeded",
        detail=None,
    )

    with pytest.raises(ValueError):
        processor_module._serialize_result(result)


def test_runtime_result_preserves_normalized_provider_usage():
    result = ExecutionResult(
        provider="claude_managed_agents", external_run_id="sesn-usage",
        status="succeeded", detail="Synthetic result",
        usage={"input_tokens": 12, "output_tokens": 8, "list_cost_minor": 3, "currency": "USD"},
    )
    payload = processor_module._serialize_result(result)
    assert payload["usage"] == result.usage


def test_runtime_result_preserves_valid_unicode():
    result = ExecutionResult(
        provider="mock",
        external_run_id="run-123",
        status="succeeded",
        detail="Synthetic test output — café.",
    )

    payload = processor_module._serialize_result(result)

    assert payload["detail"] == "Synthetic test output — café."

def test_heartbeat_stop_raises_when_thread_does_not_stop(
    monkeypatch,
    worker_context,
):
    from app.worker.processor import HeartbeatShutdownError

    ctx = worker_context

    heartbeat = LeaseHeartbeat(
        session_factory=lambda: ctx["db"],
        execution_id="execution-test",
        attempt_id="attempt-test",
        worker_id="shutdown-test",
        lease_seconds=15,
        interval_seconds=1,
    )

    class StuckThread:
        def join(self, timeout=None):
            self.timeout = timeout

        def is_alive(self):
            return True

    stuck_thread = StuckThread()
    heartbeat._thread = stuck_thread

    monkeypatch.setattr(
        "app.worker.processor.settings.worker_heartbeat_shutdown_timeout_seconds",
        0.01,
    )

    with pytest.raises(HeartbeatShutdownError):
        heartbeat.stop()

    assert stuck_thread.timeout == 0.01

def test_runtime_result_rejects_oversized_utf8_payload():
    result = ExecutionResult(
        provider="mock",
        external_run_id="run-123",
        status="succeeded",
        detail="😀" * 8500,
    )

    with pytest.raises(ValueError, match="permitted size"):
        processor_module._serialize_result(result)


def test_fail_execution_redacts_and_bounds_error_message(worker_context):
    ctx = worker_context
    execution, attempt, worker_id = start_running_attempt(ctx)

    raw_message = (
        "Authorization: Bearer super-secret "
        "api_key=private-key\n"
        + ("x" * 1200)
    )
    failed_execution, failed_attempt = fail_execution(
        ctx["db"],
        execution_id=execution.id,
        attempt_id=attempt.id,
        worker_id=worker_id,
        error_code="PROVIDER_ERROR",
        error_message=raw_message,
        retryable=False,
        provider_usage={"list_cost_minor": 251, "currency": "USD"},
    )
    ctx["db"].commit()

    assert failed_execution.result == {"usage": {"list_cost_minor": 251, "currency": "USD"}}
    assert failed_attempt.result == failed_execution.result
    assert len(failed_execution.error_message) <= 1000
    assert len(failed_attempt.error_message) <= 1000
    assert "super-secret" not in failed_execution.error_message
    assert "private-key" not in failed_execution.error_message
    assert "[REDACTED]" in failed_execution.error_message
    assert "\n" not in failed_execution.error_message
    assert failed_execution.error_message == failed_attempt.error_message


def test_queue_ready_delegation_creates_idempotent_execution(worker_context):
    from app.workforce_models import WorkforceMember, WorkforceCapability, Delegation

    ctx = worker_context
    db = ctx["db"]
    agent = db.get(Agent, ctx["agent_id"])
    parent = db.query(Task).filter_by(id=ctx["task_id"]).one()
    member = WorkforceMember(
        org_id=ctx["org_id"], workspace_id=ctx["workspace_id"],
        agent_id=agent.id, member_type="agent", name="Delegated Specialist",
        title="Delegated Specialist", department_key="engineering",
        autonomy_level=2, status="active",
    )
    db.add(member)
    db.flush()
    db.add(WorkforceCapability(
        org_id=ctx["org_id"], workspace_id=ctx["workspace_id"],
        member_id=member.id, capability_key="research.internal",
        scope="self", allowed_data_classes=["synthetic"],
        allowed_actions=["research.execute"], tool_allowlist=[],
        budget_minor=0, currency="INR", enabled=True,
    ))
    child = Task(
        org_id=ctx["org_id"], workspace_id=ctx["workspace_id"],
        title="Delegated work", description="Synthetic",
        status="queued", created_by=ctx["user_id"],
    )
    db.add(child)
    db.flush()
    row = Delegation(
        org_id=ctx["org_id"], workspace_id=ctx["workspace_id"],
        parent_task_id=parent.id, child_task_id=child.id,
        delegated_by_member_id=member.id, assigned_to_member_id=member.id,
        review_required=True, review_status="pending", status="ready",
    )
    db.add(row)
    db.commit()

    queued = queue_ready_delegations(db, limit=10)
    db.commit()
    assert queued == 1
    db.refresh(row)
    assert row.status == "queued"
    execution = db.query(Execution).filter_by(task_id=child.id).one()
    assert execution.status == ExecutionStatus.queued
    assert execution.idempotency_key == f"delegation:{row.id}"

    queued_again = queue_ready_delegations(db, limit=10)
    db.commit()
    assert queued_again == 0
    assert db.query(Execution).filter_by(task_id=child.id).count() == 1


def test_dependency_blocked_delegation_queues_after_prerequisite_succeeds(worker_context):
    from app.workforce_models import WorkforceMember, WorkforceCapability, Delegation

    ctx = worker_context
    db = ctx["db"]
    agent = db.get(Agent, ctx["agent_id"])
    parent = db.query(Task).filter_by(id=ctx["task_id"]).one()
    prerequisite = Task(
        org_id=ctx["org_id"], workspace_id=ctx["workspace_id"],
        title="Prerequisite", status="queued", created_by=ctx["user_id"],
    )
    db.add(prerequisite)
    db.flush()
    member = WorkforceMember(
        org_id=ctx["org_id"], workspace_id=ctx["workspace_id"],
        agent_id=agent.id, member_type="agent", name="Dependent Specialist",
        title="Dependent Specialist", department_key="engineering",
        autonomy_level=2, status="active",
    )
    db.add(member)
    db.flush()
    db.add(WorkforceCapability(
        org_id=ctx["org_id"], workspace_id=ctx["workspace_id"],
        member_id=member.id, capability_key="research.internal",
        scope="self", allowed_data_classes=["synthetic"],
        allowed_actions=["research.execute"], tool_allowlist=[],
        budget_minor=0, currency="INR", enabled=True,
    ))
    child = Task(
        org_id=ctx["org_id"], workspace_id=ctx["workspace_id"],
        title="Dependent work", status="blocked", created_by=ctx["user_id"],
    )
    db.add(child)
    db.flush()
    row = Delegation(
        org_id=ctx["org_id"], workspace_id=ctx["workspace_id"],
        parent_task_id=parent.id, child_task_id=child.id,
        delegated_by_member_id=member.id, assigned_to_member_id=member.id,
        dependency_task_id=prerequisite.id, review_required=False,
        review_status="pending", status="blocked",
    )
    db.add(row)
    db.commit()

    assert queue_ready_delegations(db, limit=10) == 0
    db.commit()
    assert db.query(Execution).filter_by(task_id=child.id).count() == 0

    prerequisite.status = "succeeded"
    db.commit()
    assert queue_ready_delegations(db, limit=10) == 1
    db.commit()
    db.refresh(row)
    assert row.status == "queued"
    assert db.query(Execution).filter_by(task_id=child.id).one().status == ExecutionStatus.queued


def test_delegated_task_state_tracks_execution_and_review_gate(worker_context):
    from app.workforce_models import WorkforceMember, WorkforceCapability, Delegation

    ctx = worker_context
    db = ctx["db"]
    agent = db.get(Agent, ctx["agent_id"])
    parent = db.query(Task).filter_by(id=ctx["task_id"]).one()
    member = WorkforceMember(
        org_id=ctx["org_id"], workspace_id=ctx["workspace_id"],
        agent_id=agent.id, member_type="agent", name="Lifecycle Specialist",
        title="Lifecycle Specialist", department_key="engineering",
        autonomy_level=2, status="active",
    )
    db.add(member)
    db.flush()
    db.add(WorkforceCapability(
        org_id=ctx["org_id"], workspace_id=ctx["workspace_id"],
        member_id=member.id, capability_key="research.internal",
        scope="self", allowed_data_classes=["synthetic"],
        allowed_actions=["research.execute"], tool_allowlist=[],
        budget_minor=0, currency="INR", enabled=True,
    ))
    child = Task(
        org_id=ctx["org_id"], workspace_id=ctx["workspace_id"],
        title="Lifecycle work", status="queued", created_by=ctx["user_id"],
    )
    db.add(child)
    db.flush()
    row = Delegation(
        org_id=ctx["org_id"], workspace_id=ctx["workspace_id"],
        parent_task_id=parent.id, child_task_id=child.id,
        delegated_by_member_id=member.id, assigned_to_member_id=member.id,
        review_required=True, review_status="pending", status="queued",
    )
    db.add(row)
    db.flush()
    execution = create_execution(
        db, org_id=ctx["org_id"], workspace_id=ctx["workspace_id"],
        task_id=child.id, agent_id=agent.id, requested_by=ctx["user_id"],
        idempotency_key=f"delegation:{row.id}",
    )
    db.commit()
    claimed = claim_next_execution(db, worker_id="delegation-lifecycle", lease_seconds=30)
    assert claimed is not None
    _, attempt = claimed
    db.commit()
    start_execution(
        db, execution_id=execution.id, attempt_id=attempt.id,
        worker_id="delegation-lifecycle", lease_seconds=30,
    )
    db.commit()
    db.refresh(child)
    db.refresh(row)
    assert child.status == "running"
    assert row.status == "running"

    complete_execution(
        db, execution_id=execution.id, attempt_id=attempt.id,
        worker_id="delegation-lifecycle",
        result={"provider": "mock", "detail": "synthetic result"},
    )
    db.commit()
    db.refresh(child)
    db.refresh(row)
    assert child.status == "succeeded"
    assert row.status == "awaiting_review"

def _create_plan_draft_worker_context(ctx, detail_label="valid"):
    import json
    from app.models import Task
    from app.workforce_models import OrchestrationPlanDraft, WorkforceMember
    from app.workforce_service import initialize_workforce

    db = ctx["db"]
    initialize_workforce(
        db, org_id=ctx["org_id"], workspace_id=ctx["workspace_id"]
    )
    chief = db.query(WorkforceMember).filter_by(
        org_id=ctx["org_id"], workspace_id=ctx["workspace_id"],
        department_key="office_chief_of_staff",
    ).one()
    task = db.get(Task, ctx["task_id"])
    execution = create_worker_execution(ctx)
    detail = (
        json.dumps({
            "schema_version": 1,
            "summary": "A bounded synthetic implementation plan",
            "tasks": [{
                "title": "Prepare a synthetic review",
                "description": "Prepare a bounded implementation and validation outline.",
                "department_key": "quality_assurance_security",
                "depends_on_ordinal": None,
                "acceptance_criteria": ["The review has explicit pass criteria."],
                "review_required": True,
            }],
            "risks": [],
            "founder_decisions": [],
        })
        if detail_label == "valid" else "not a JSON plan"
    )
    draft = OrchestrationPlanDraft(
        org_id=ctx["org_id"], workspace_id=ctx["workspace_id"],
        task_id=task.id, execution_id=execution.id,
        requested_by_user_id=ctx["user_id"], created_by_member_id=chief.id,
        idempotency_key=f"draft-{uuid.uuid4().hex}",
        objective="Prepare a synthetic quality review plan",
        plan_title="Synthetic quality plan",
        status="queued", suggested_plan={},
    )
    db.add(draft)
    db.flush()
    execution.request_metadata = {
        "purpose": "workforce.plan_draft",
        "plan_draft_id": draft.id,
        "schema_version": 1,
    }
    db.commit()
    return execution, draft


def _complete_worker_execution(ctx, execution):
    db = ctx["db"]
    claimed = claim_next_execution(
        db, worker_id="plan-draft-test-worker", lease_seconds=30,
    )
    assert claimed is not None
    claimed_execution, attempt = claimed
    assert claimed_execution.id == execution.id
    db.commit()
    start_execution(
        db, execution_id=execution.id, attempt_id=attempt.id,
        worker_id="plan-draft-test-worker", lease_seconds=30,
    )
    db.commit()
    complete_execution(
        db, execution_id=execution.id, attempt_id=attempt.id,
        worker_id="plan-draft-test-worker",
        result={
            "provider": "mock",
            "external_run_id": "synthetic-plan-draft",
            "status": "succeeded",
            "detail": ctx["plan_detail"],
        },
    )
    db.commit()


def test_plan_draft_execution_becomes_founder_reviewable(worker_context):
    from app.workforce_models import OrchestrationPlanDraft
    from app.models import Task

    ctx = worker_context
    execution, draft = _create_plan_draft_worker_context(ctx)
    import json
    ctx["plan_detail"] = json.dumps({
        "schema_version": 1,
        "summary": "A bounded synthetic implementation plan",
        "tasks": [{
            "title": "Prepare a synthetic review",
            "description": "Prepare a bounded implementation and validation outline.",
            "department_key": "quality_assurance_security",
            "depends_on_ordinal": None,
            "acceptance_criteria": ["The review has explicit pass criteria."],
            "review_required": True,
        }],
        "risks": [],
        "founder_decisions": [],
    })
    _complete_worker_execution(ctx, execution)
    ctx["db"].refresh(draft)
    ctx["db"].expire_all()
    saved = ctx["db"].get(OrchestrationPlanDraft, draft.id)
    task = ctx["db"].get(Task, draft.task_id)
    assert saved.status == "ready_for_review"
    assert saved.suggested_plan["tasks"][0]["department_key"] == "quality_assurance_security"
    assert task.status == "awaiting_review"


def test_invalid_plan_draft_output_is_never_reviewable(worker_context):
    from app.workforce_models import OrchestrationPlanDraft
    from app.models import Task

    ctx = worker_context
    execution, draft = _create_plan_draft_worker_context(ctx, detail_label="invalid")
    ctx["plan_detail"] = "This is not JSON."
    _complete_worker_execution(ctx, execution)
    ctx["db"].expire_all()
    saved = ctx["db"].get(OrchestrationPlanDraft, draft.id)
    task = ctx["db"].get(Task, draft.task_id)
    assert saved.status == "invalid_output"
    assert saved.error_code == "PLAN_DRAFT_OUTPUT_INVALID"
    assert task.status == "failed"



def test_processor_injects_attempt_scoped_os_tool_executor_for_managed_agents(worker_context, monkeypatch):
    ctx = worker_context
    agent = ctx["db"].get(Agent, ctx["agent_id"])
    agent.runtime = "claude_managed_agents"
    ctx["db"].commit()

    import app.execution_service as execution_service_module
    monkeypatch.setattr(execution_service_module, "is_runtime_available", lambda _name: True)
    execution = create_worker_execution(ctx)
    session_factory = sessionmaker(
        bind=ctx["db"].get_bind(),
        autoflush=False,
        autocommit=False,
    )
    captured = {}

    def fake_builder(**kwargs):
        captured.update(kwargs)
        return lambda name, payload, event_id: {
            "tool": name,
            "payload": payload,
            "event_id": event_id,
        }

    class FakeManagedRuntime:
        def start(self, request):
            assert request.execute_custom_tool is not None
            result = request.execute_custom_tool(
                "os_system_health_read", {}, "sevt_processor_wire"
            )
            assert result["event_id"] == "sevt_processor_wire"
            return ExecutionResult(
                "claude_managed_agents", "sesn_processor_wire", "succeeded", "done"
            )

    monkeypatch.setattr(processor_module, "build_machine_tool_executor", fake_builder)
    monkeypatch.setattr(processor_module, "get_runtime", lambda _runtime_name: FakeManagedRuntime())
    monkeypatch.setattr(settings, "claude_managed_timeout_seconds", 600)

    processed_id = process_one_execution(
        worker_id="processor-tool-wire",
        session_factory=session_factory,
    )
    assert processed_id == execution.id
    assert captured["execution_id"] == execution.id
    assert captured["attempt_id"]
    assert captured["worker_id"] == "processor-tool-wire"
    assert captured["session_ttl_seconds"] == 600

    ctx["db"].expire_all()
    assert ctx["db"].get(Execution, execution.id).status == ExecutionStatus.succeeded


def test_processor_persists_usage_when_provider_budget_requires_review(worker_context, monkeypatch):
    from app.integrations.runtime import RuntimeManualReviewRequired
    ctx = worker_context
    execution, session_factory = mock_worker_context(ctx)

    class BudgetReachedRuntime:
        def start(self, request):
            raise RuntimeManualReviewRequired(
                "Provider session budget reached.",
                usage={"input_tokens": 100, "output_tokens": 40,
                       "list_cost_minor": 251, "currency": "USD"},
            )

    monkeypatch.setattr("app.worker.processor.get_runtime", lambda _name: BudgetReachedRuntime())
    processed_id = process_one_execution(worker_id="provider-budget-review", session_factory=session_factory)
    assert processed_id == execution.id
    ctx["db"].expire_all()
    saved = ctx["db"].get(Execution, execution.id)
    attempt = ctx["db"].query(ExecutionAttempt).filter_by(execution_id=execution.id).one()
    assert saved.status == ExecutionStatus.failed
    assert saved.error_code == "RUNTIME_REQUIRES_REVIEW"
    assert saved.provider_usage == {"input_tokens": 100, "output_tokens": 40,
                                    "list_cost_minor": 251, "currency": "USD"}
    assert attempt.result == saved.result



def test_managed_agents_usage_adds_distinct_provider_sessions(worker_context):
    ctx = worker_context
    db = ctx["db"]
    execution = create_worker_execution(ctx)
    execution.runtime = "claude_managed_agents"
    first_usage = {"input_tokens": 100, "output_tokens": 20, "list_cost_minor": 10,
                   "currency": "USD"}
    second_usage = {"input_tokens": 50, "output_tokens": 30, "list_cost_minor": 7,
                    "currency": "USD"}
    for number, session_id, usage in (
        (1, "sesn-one", first_usage), (2, "sesn-two", second_usage),
    ):
        db.add(ExecutionAttempt(
            execution_id=execution.id, attempt_number=number,
            runtime="claude_managed_agents", external_run_id=session_id,
            status=ExecutionAttemptStatus.failed,
            result={"usage": usage},
        ))
    db.flush()

    assert _aggregate_provider_usage(db, execution.id) == {
        "input_tokens": 150, "output_tokens": 50, "list_cost_minor": 17,
        "currency": "USD",
    }

def test_managed_agents_usage_uses_latest_cumulative_snapshot_for_resumed_session(worker_context):
    ctx = worker_context
    db = ctx["db"]
    execution, first_attempt, worker_id = start_running_attempt(ctx)
    execution.runtime = "claude_managed_agents"
    first_attempt.runtime = "claude_managed_agents"
    first_attempt.external_run_id = "sesn-shared"
    first_usage = {
        "input_tokens": 100, "output_tokens": 20, "list_cost_minor": 10,
        "currency": "USD", "active_seconds": 1.5,
        "server_tool_use": {"web_search_requests": 1, "web_fetch_requests": 0},
    }
    fail_execution(
        db, execution_id=execution.id, attempt_id=first_attempt.id, worker_id=worker_id,
        error_code="RUNTIME_REQUIRES_REVIEW", error_message="First attempt paused.",
        retryable=True, provider_usage=first_usage,
    )
    now = datetime.now(timezone.utc)
    execution.status = ExecutionStatus.running
    execution.attempt_count = 2
    execution.next_retry_at = None
    second_attempt = ExecutionAttempt(
        execution_id=execution.id, attempt_number=2, worker_id=worker_id,
        runtime=execution.runtime, external_run_id="sesn-shared",
        status=ExecutionAttemptStatus.running,
        lease_expires_at=now + timedelta(seconds=120), heartbeat_at=now, started_at=now,
    )
    db.add(second_attempt); db.flush()
    second_usage = {
        "input_tokens": 150, "output_tokens": 50, "list_cost_minor": 17,
        "currency": "USD", "active_seconds": 2.5,
        "server_tool_use": {"web_search_requests": 1, "web_fetch_requests": 1},
    }
    complete_execution(
        db, execution_id=execution.id, attempt_id=second_attempt.id, worker_id=worker_id,
        result={"provider": "claude_managed_agents", "external_run_id": "sesn-shared",
                "status": "succeeded", "detail": "Completed.", "usage": second_usage},
    )
    db.commit()
    assert execution.provider_usage == second_usage
    assert first_attempt.result["usage"] == first_usage
    assert second_attempt.result["usage"] == second_usage



def test_abandoned_managed_agent_session_usage_is_reconciled_idempotently(worker_context):
    from sqlalchemy.orm import sessionmaker
    from app.provider_usage_reconciliation import reconcile_abandoned_managed_agent_usage

    ctx = worker_context
    db = ctx["db"]
    execution = create_worker_execution(ctx)
    execution.runtime = "claude_managed_agents"
    execution.status = ExecutionStatus.retry_wait
    attempt = ExecutionAttempt(
        execution_id=execution.id,
        attempt_number=1,
        runtime="claude_managed_agents",
        status=ExecutionAttemptStatus.abandoned,
        external_run_id="sesn_reconcile",
        result=None,
        finished_at=datetime.now(timezone.utc),
    )
    db.add(attempt)
    db.commit()

    class Runtime:
        calls = 0
        usage = {
            "input_tokens": 31,
            "output_tokens": 12,
            "list_cost_minor": 9,
            "currency": "USD",
        }

        def fetch_idle_session_usage(self, session_id):
            self.calls += 1
            assert session_id == "sesn_reconcile"
            return self.usage

    runtime = Runtime()
    session_factory = sessionmaker(bind=db.get_bind(), autoflush=False, autocommit=False)

    result = reconcile_abandoned_managed_agent_usage(
        session_factory,
        runtime=runtime,
        limit=5,
    )

    assert result == {"reconciled": 1, "pending": 0, "skipped": 0}
    db.expire_all()
    persisted_attempt = db.get(ExecutionAttempt, attempt.id)
    persisted_execution = db.get(Execution, execution.id)
    assert persisted_attempt.result["usage"] == {
        "input_tokens": 31,
        "output_tokens": 12,
        "list_cost_minor": 9,
        "currency": "USD",
    }
    assert persisted_attempt.result["usage_reconciliation"]["status"] == "reconciled"
    assert persisted_execution.result["usage"]["list_cost_minor"] == 9

    second = reconcile_abandoned_managed_agent_usage(
        session_factory,
        runtime=runtime,
        limit=5,
    )
    assert second == {"reconciled": 0, "pending": 0, "skipped": 1}
    assert runtime.calls == 1

    # A later idle snapshot is cumulative and may have increased after the
    # earlier idle point. Refresh it rather than freezing the first snapshot.
    runtime.usage = {
        "input_tokens": 44,
        "output_tokens": 19,
        "list_cost_minor": 12,
        "currency": "USD",
    }
    third = reconcile_abandoned_managed_agent_usage(
        session_factory,
        runtime=runtime,
        limit=5,
        now=datetime.now(timezone.utc) + timedelta(seconds=301),
    )
    assert third == {"reconciled": 1, "pending": 0, "skipped": 0}
    db.expire_all()
    assert db.get(ExecutionAttempt, attempt.id).result["usage"]["list_cost_minor"] == 12
    assert db.get(Execution, execution.id).result["usage"]["list_cost_minor"] == 12
    assert runtime.calls == 2


def test_non_idle_managed_agent_usage_reconciliation_is_deferred(worker_context):
    from sqlalchemy.orm import sessionmaker
    from app.provider_usage_reconciliation import reconcile_abandoned_managed_agent_usage

    ctx = worker_context
    db = ctx["db"]
    execution = create_worker_execution(ctx)
    execution.runtime = "claude_managed_agents"
    execution.status = ExecutionStatus.retry_wait
    attempt = ExecutionAttempt(
        execution_id=execution.id,
        attempt_number=1,
        runtime="claude_managed_agents",
        status=ExecutionAttemptStatus.abandoned,
        external_run_id="sesn_still_running",
        result=None,
        finished_at=datetime.now(timezone.utc),
    )
    db.add(attempt)
    db.commit()

    class Runtime:
        calls = 0

        def fetch_idle_session_usage(self, session_id):
            self.calls += 1
            return None

    runtime = Runtime()
    session_factory = sessionmaker(bind=db.get_bind(), autoflush=False, autocommit=False)
    first = reconcile_abandoned_managed_agent_usage(
        session_factory,
        runtime=runtime,
        limit=5,
    )
    assert first == {"reconciled": 0, "pending": 1, "skipped": 0}

    db.expire_all()
    persisted = db.get(ExecutionAttempt, attempt.id)
    assert persisted.result["usage_reconciliation"]["status"] == "pending"

    second = reconcile_abandoned_managed_agent_usage(
        session_factory,
        runtime=runtime,
        limit=5,
    )
    assert second == {"reconciled": 0, "pending": 0, "skipped": 1}
    assert runtime.calls == 1



def test_provider_usage_read_failure_is_backed_off(worker_context):
    from sqlalchemy.orm import sessionmaker
    from app.provider_usage_reconciliation import reconcile_abandoned_managed_agent_usage

    ctx = worker_context
    db = ctx["db"]
    execution = create_worker_execution(ctx)
    execution.runtime = "claude_managed_agents"
    execution.status = ExecutionStatus.retry_wait
    attempt = ExecutionAttempt(
        execution_id=execution.id,
        attempt_number=1,
        runtime="claude_managed_agents",
        status=ExecutionAttemptStatus.abandoned,
        external_run_id="sesn_read_error",
        result=None,
        finished_at=datetime.now(timezone.utc),
    )
    db.add(attempt)
    db.commit()

    class Runtime:
        calls = 0

        def fetch_idle_session_usage(self, _session_id):
            self.calls += 1
            raise RuntimeError("provider request failed with sensitive request metadata")

    runtime = Runtime()
    session_factory = sessionmaker(bind=db.get_bind(), autoflush=False, autocommit=False)
    first = reconcile_abandoned_managed_agent_usage(
        session_factory, runtime=runtime, limit=5,
    )
    assert first == {"reconciled": 0, "pending": 1, "skipped": 0}

    db.expire_all()
    persisted = db.get(ExecutionAttempt, attempt.id)
    assert persisted.result["usage_reconciliation"]["reason"] == "provider_read_failed"

    second = reconcile_abandoned_managed_agent_usage(
        session_factory, runtime=runtime, limit=5,
    )
    assert second == {"reconciled": 0, "pending": 0, "skipped": 1}
    assert runtime.calls == 1


def test_provider_usage_snapshot_is_not_written_after_execution_resumes(worker_context):
    from sqlalchemy.orm import sessionmaker
    from app.provider_usage_reconciliation import reconcile_abandoned_managed_agent_usage

    ctx = worker_context
    db = ctx["db"]
    execution = create_worker_execution(ctx)
    execution.runtime = "claude_managed_agents"
    execution.status = ExecutionStatus.retry_wait
    attempt = ExecutionAttempt(
        execution_id=execution.id,
        attempt_number=1,
        runtime="claude_managed_agents",
        status=ExecutionAttemptStatus.abandoned,
        external_run_id="sesn_resumed",
        result=None,
        finished_at=datetime.now(timezone.utc),
    )
    db.add(attempt)
    db.commit()

    class Runtime:
        def fetch_idle_session_usage(self, _session_id):
            execution.status = ExecutionStatus.running
            db.commit()
            return {"input_tokens": 5, "output_tokens": 2}

    session_factory = sessionmaker(bind=db.get_bind(), autoflush=False, autocommit=False)
    result = reconcile_abandoned_managed_agent_usage(
        session_factory, runtime=Runtime(), limit=5,
    )
    assert result == {"reconciled": 0, "pending": 0, "skipped": 1}

    db.expire_all()
    persisted = db.get(ExecutionAttempt, attempt.id)
    assert persisted.result is None



def test_failed_managed_agent_attempt_usage_is_reconciled(worker_context):
    from sqlalchemy.orm import sessionmaker
    from app.provider_usage_reconciliation import reconcile_abandoned_managed_agent_usage

    ctx = worker_context
    db = ctx["db"]
    execution = create_worker_execution(ctx)
    execution.runtime = "claude_managed_agents"
    execution.status = ExecutionStatus.failed
    attempt = ExecutionAttempt(
        execution_id=execution.id,
        attempt_number=1,
        runtime="claude_managed_agents",
        status=ExecutionAttemptStatus.failed,
        external_run_id="sesn_failed_attempt",
        result=None,
        finished_at=datetime.now(timezone.utc),
    )
    db.add(attempt)
    db.commit()

    class Runtime:
        def fetch_idle_session_usage(self, session_id):
            assert session_id == "sesn_failed_attempt"
            return {"input_tokens": 8, "output_tokens": 3}

    session_factory = sessionmaker(bind=db.get_bind(), autoflush=False, autocommit=False)
    result = reconcile_abandoned_managed_agent_usage(
        session_factory, runtime=Runtime(), limit=5,
    )

    assert result == {"reconciled": 1, "pending": 0, "skipped": 0}
    db.expire_all()
    assert db.get(ExecutionAttempt, attempt.id).result["usage"] == {
        "input_tokens": 8,
        "output_tokens": 3,
    }
    assert db.get(Execution, execution.id).result["usage"]["output_tokens"] == 3



def test_processor_links_retried_attempt_to_existing_managed_agent_session(worker_context, monkeypatch):
    ctx = worker_context
    db = ctx["db"]
    execution = create_worker_execution(ctx, max_attempts=2)
    execution.runtime = "claude_managed_agents"
    execution.attempt_count = 1
    execution.status = ExecutionStatus.queued
    previous_usage = {
        "input_tokens": 100,
        "output_tokens": 50,
        "list_cost_minor": 10,
        "currency": "USD",
    }
    previous_attempt = ExecutionAttempt(
        execution_id=execution.id,
        attempt_number=1,
        runtime="claude_managed_agents",
        status=ExecutionAttemptStatus.failed,
        external_run_id="sesn_shared_retry",
        result={"usage": previous_usage},
        finished_at=datetime.now(timezone.utc),
    )
    db.add(previous_attempt)
    db.commit()

    class Runtime:
        def start(self, request):
            assert request.external_run_id == "sesn_shared_retry"
            # Simulate the resumed provider session returning its newer
            # cumulative snapshot; the adapter does not create a new session.
            return ExecutionResult(
                provider="claude_managed_agents",
                external_run_id="sesn_shared_retry",
                status="succeeded",
                detail="Resumed session completed.",
                usage={
                    "input_tokens": 120,
                    "output_tokens": 60,
                    "list_cost_minor": 15,
                    "currency": "USD",
                },
            )

    monkeypatch.setattr("app.worker.processor.get_runtime", lambda _name: Runtime())
    session_factory = sessionmaker(bind=db.get_bind(), autoflush=False, autocommit=False)
    processed = process_one_execution(
        worker_id="worker-resume-session",
        session_factory=session_factory,
    )

    assert processed == execution.id
    db.expire_all()
    attempts = (
        db.query(ExecutionAttempt)
        .filter_by(execution_id=execution.id)
        .order_by(ExecutionAttempt.attempt_number.asc())
        .all()
    )
    assert len(attempts) == 2
    assert attempts[1].external_run_id == "sesn_shared_retry"
    assert db.get(Execution, execution.id).result["usage"]["list_cost_minor"] == 15
