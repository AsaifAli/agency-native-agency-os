import os
import uuid

import pytest

from app.config import settings
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.execution_service import create_execution
from app.models import (
    Agent,
    AuditEvent,
    DataClass,
    Execution,
    ExecutionAttempt,
    Organization,
    Task,
    User,
    Workspace,
)
from app.worker_service import (
    claim_next_execution,
    recover_expired_execution_leases,
)
from datetime import datetime, timedelta, timezone
import app.security_models  # noqa: F401 — register security FK metadata
from app.telephony.models import OutboxEvent
from app.outbox_service import reconcile_outbox_events, claim_outbox_batch


def test_postgres_workers_claim_different_executions(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(settings, "mock_runtime_enabled", True)
    database_url = os.getenv("AGENCY_OS_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set AGENCY_OS_TEST_DATABASE_URL to run PostgreSQL concurrency test")

    parsed_url = make_url(database_url)
    assert parsed_url.get_backend_name() == "postgresql"
    assert parsed_url.database == "agency_os_worker_test", (
        "Safety check: this test may only use agency_os_worker_test"
    )

    engine = create_engine(database_url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    org_id = None
    workspace_id = None
    task_id = None
    agent_id = None
    user_id = None
    execution_ids = []

    try:
        with engine.connect() as connection:
            database_name = connection.execute(
                text("SELECT current_database()")
            ).scalar_one()
            assert database_name == "agency_os_worker_test"

            migration_version = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            assert migration_version, "Database migrations must be applied"

        setup = Session()
        try:
            suffix = uuid.uuid4().hex[:12]

            user = User(
                email=f"pg-worker-{suffix}@test.local",
                display_name="PostgreSQL Worker Test",
            )
            org = Organization(name=f"PostgreSQL Worker Test {suffix}")
            setup.add_all([user, org])
            setup.flush()

            workspace = Workspace(
                id=f"pg-ws-{suffix}",
                org_id=org.id,
                name="PostgreSQL Worker Test Workspace",
            )
            setup.add(workspace)
            setup.flush()

            agent = Agent(
                org_id=org.id,
                workspace_id=workspace.id,
                name=f"PostgreSQL Worker Agent {suffix}",
                runtime="mock",
                data_class=DataClass.synthetic,
                enabled=True,
            )
            task = Task(
                org_id=org.id,
                workspace_id=workspace.id,
                title="PostgreSQL concurrent claim test",
                description="Synthetic test task",
                created_by=user.id,
            )
            setup.add_all([agent, task])
            setup.flush()

            org_id = org.id
            workspace_id = workspace.id
            task_id = task.id
            agent_id = agent.id
            user_id = user.id

            first = create_execution(
                setup,
                org_id=org_id,
                workspace_id=workspace_id,
                task_id=task_id,
                agent_id=agent_id,
                requested_by=user_id,
                idempotency_key=f"pg-worker-{suffix}-1",
            )
            second = create_execution(
                setup,
                org_id=org_id,
                workspace_id=workspace_id,
                task_id=task_id,
                agent_id=agent_id,
                requested_by=user_id,
                idempotency_key=f"pg-worker-{suffix}-2",
            )
            execution_ids = [first.id, second.id]
            setup.commit()
        finally:
            setup.close()

        worker_a = Session()
        worker_b = Session()

        try:
            # Both sessions have a short lock timeout. If SKIP LOCKED
            # regresses, the second claim fails instead of hanging.
            worker_a.execute(text("SET LOCAL lock_timeout = '2s'"))
            worker_b.execute(text("SET LOCAL lock_timeout = '2s'"))

            claim_a = claim_next_execution(
                worker_a,
                worker_id=f"postgres-worker-a-{uuid.uuid4().hex[:8]}",
            )
            assert claim_a is not None

            # Worker A deliberately keeps its transaction open and its
            # execution row locked while worker B attempts to claim.
            claim_b = claim_next_execution(
                worker_b,
                worker_id=f"postgres-worker-b-{uuid.uuid4().hex[:8]}",
            )
            assert claim_b is not None

            execution_a, attempt_a = claim_a
            execution_b, attempt_b = claim_b

            assert execution_a.id != execution_b.id
            assert {execution_a.id, execution_b.id} == set(execution_ids)
            assert attempt_a.execution_id == execution_a.id
            assert attempt_b.execution_id == execution_b.id
            assert attempt_a.attempt_number == 1
            assert attempt_b.attempt_number == 1
            assert attempt_a.worker_id != attempt_b.worker_id

            worker_a.commit()
            worker_b.commit()
        finally:
            worker_a.rollback()
            worker_b.rollback()
            worker_a.close()
            worker_b.close()

        verification = Session()
        try:
            attempts = (
                verification.query(ExecutionAttempt)
                .filter(ExecutionAttempt.execution_id.in_(execution_ids))
                .all()
            )
            assert len(attempts) == 2
            assert {attempt.execution_id for attempt in attempts} == set(execution_ids)

            events = (
                verification.query(AuditEvent)
                .filter(
                    AuditEvent.event_type == "execution.claimed",
                    AuditEvent.resource_id.in_(execution_ids),
                )
                .all()
            )
            assert len(events) == 2
            assert {event.resource_id for event in events} == set(execution_ids)
        finally:
            verification.close()

        # Simulate a worker process disappearing after its claim was committed.
        # The persisted lease expiry must make the attempt recoverable.
        recovery = Session()
        try:
            crashed_attempt = (
                recovery.query(ExecutionAttempt)
                .filter(ExecutionAttempt.execution_id == execution_ids[0])
                .one()
            )
            crashed_attempt.lease_expires_at = (
                datetime.now(timezone.utc) - timedelta(seconds=5)
            )
            recovery.commit()

            recovered_count = recover_expired_execution_leases(
                recovery,
                base_delay_seconds=5,
                max_delay_seconds=30,
            )
            assert recovered_count == 1
            recovery.commit()

            recovered_execution = recovery.query(Execution).filter(
                Execution.id == execution_ids[0]
            ).one()
            recovered_attempt = recovery.query(ExecutionAttempt).filter(
                ExecutionAttempt.id == crashed_attempt.id
            ).one()
            assert recovered_execution.status.value == "retry_wait"
            assert recovered_execution.next_retry_at is not None
            assert recovered_attempt.status.value == "abandoned"
            assert recovered_attempt.lease_expires_at is None
            assert recovered_attempt.error_code == "WORKER_LEASE_EXPIRED"

            recovery_event = recovery.query(AuditEvent).filter_by(
                event_type="execution.attempt_abandoned",
                resource_id=recovered_attempt.id,
            ).one()
            assert recovery_event.payload["error_code"] == "WORKER_LEASE_EXPIRED"
            assert recovery_event.payload["worker_id"].startswith(
                "postgres-worker-"
            )
        finally:
            recovery.close()

    finally:
        # Remove only records created by this test.
        if org_id is not None:
            cleanup = Session()
            try:
                if execution_ids:
                    # Recovery also emits attempt-scoped audit rows.
                    cleanup.query(AuditEvent).filter(
                        AuditEvent.org_id == org_id
                    ).delete(synchronize_session=False)
                    cleanup.query(ExecutionAttempt).filter(
                        ExecutionAttempt.execution_id.in_(execution_ids)
                    ).delete(synchronize_session=False)
                    cleanup.query(Execution).filter(
                        Execution.id.in_(execution_ids)
                    ).delete(synchronize_session=False)

                if task_id:
                    cleanup.query(Task).filter(Task.id == task_id).delete(
                        synchronize_session=False
                    )
                if agent_id:
                    cleanup.query(Agent).filter(Agent.id == agent_id).delete(
                        synchronize_session=False
                    )
                if workspace_id:
                    cleanup.query(Workspace).filter(
                        Workspace.id == workspace_id
                    ).delete(synchronize_session=False)
                if user_id:
                    cleanup.query(User).filter(User.id == user_id).delete(
                        synchronize_session=False
                    )
                cleanup.query(Organization).filter(
                    Organization.id == org_id
                ).delete(synchronize_session=False)
                cleanup.commit()
            except Exception:
                cleanup.rollback()
                raise
            finally:
                cleanup.close()

        engine.dispose()

def test_postgres_outbox_workers_claim_different_events(monkeypatch):
    """PostgreSQL SKIP LOCKED prevents two dispatchers claiming one event."""
    from app.telephony.models import OutboxEvent
    from app.outbox_service import claim_outbox_batch

    database_url = os.getenv("AGENCY_OS_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set AGENCY_OS_TEST_DATABASE_URL to run PostgreSQL outbox concurrency test")

    parsed_url = make_url(database_url)
    assert parsed_url.get_backend_name() == "postgresql"
    assert parsed_url.database == "agency_os_worker_test", (
        "Safety check: this test may only use agency_os_worker_test"
    )

    engine = create_engine(database_url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    org_id = workspace_id = None
    event_ids = []
    suffix = uuid.uuid4().hex[:12]
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT current_database()")).scalar_one() == "agency_os_worker_test"
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()

        setup = Session()
        try:
            org = Organization(name=f"Outbox PG Test {suffix}")
            setup.add(org)
            setup.flush()
            workspace = Workspace(id=f"outbox-pg-{suffix}", org_id=org.id, name="Outbox PG Test")
            setup.add(workspace)
            setup.flush()
            org_id, workspace_id = org.id, workspace.id
            for index in range(2):
                event = OutboxEvent(
                    org_id=org_id, workspace_id=workspace_id,
                    event_type="test.postgres.claim", schema_version=1,
                    aggregate_type="test", aggregate_id=f"aggregate-{index}-{suffix}",
                    idempotency_key=f"outbox-pg-{suffix}-{index}", payload={"synthetic": True},
                )
                setup.add(event)
                setup.flush()
                event_ids.append(event.id)
            setup.commit()
        finally:
            setup.close()

        worker_a, worker_b = Session(), Session()
        try:
            worker_a.execute(text("SET LOCAL lock_timeout = '2s'"))
            worker_b.execute(text("SET LOCAL lock_timeout = '2s'"))
            claim_a = claim_outbox_batch(
                worker_a, worker_id=f"outbox-a-{suffix}",
                event_types={"test.postgres.claim"}, limit=1,
            )
            assert len(claim_a) == 1
            claim_b = claim_outbox_batch(
                worker_b, worker_id=f"outbox-b-{suffix}",
                event_types={"test.postgres.claim"}, limit=1,
            )
            assert len(claim_b) == 1
            assert claim_a[0].id != claim_b[0].id
            assert {claim_a[0].id, claim_b[0].id} == set(event_ids)
            worker_a.commit()
            worker_b.commit()
        finally:
            worker_a.rollback()
            worker_b.rollback()
            worker_a.close()
            worker_b.close()
    finally:
        if org_id:
            cleanup = Session()
            try:
                cleanup.query(OutboxEvent).filter(OutboxEvent.id.in_(event_ids)).delete(synchronize_session=False)
                cleanup.query(Workspace).filter(Workspace.id == workspace_id).delete(synchronize_session=False)
                cleanup.query(Organization).filter(Organization.id == org_id).delete(synchronize_session=False)
                cleanup.commit()
            finally:
                cleanup.close()
        engine.dispose()


def test_postgres_outbox_recovers_expired_lease_and_dead_letters_exhausted_event():
    database_url = os.getenv("AGENCY_OS_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set AGENCY_OS_TEST_DATABASE_URL to run PostgreSQL recovery test")

    parsed_url = make_url(database_url)
    assert parsed_url.get_backend_name() == "postgresql"
    assert parsed_url.database == "agency_os_worker_test", (
        "Safety check: this test may only use agency_os_worker_test"
    )

    engine = create_engine(database_url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    org_id = None
    workspace_id = None
    event_ids = []
    suffix = uuid.uuid4().hex[:12]
    event_type = f"test.postgres.recovery.{suffix}"

    try:
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT current_database()")
            ).scalar_one() == "agency_os_worker_test"

            assert connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()

        setup = Session()
        try:
            org = Organization(name=f"Outbox Recovery Test {suffix}")
            setup.add(org)
            setup.flush()

            workspace = Workspace(
                id=f"outbox-recovery-{suffix}",
                org_id=org.id,
                name="Outbox Recovery Test",
            )
            setup.add(workspace)
            setup.flush()

            org_id = org.id
            workspace_id = workspace.id
            expired_at = datetime.now(timezone.utc) - timedelta(minutes=5)

            expired_event = OutboxEvent(
                org_id=org_id,
                workspace_id=workspace_id,
                event_type=event_type,
                schema_version=1,
                aggregate_type="test",
                aggregate_id=f"expired-{suffix}",
                idempotency_key=f"recovery-expired-{suffix}",
                payload={"synthetic": True},
                status="processing",
                attempts=2,
                max_attempts=8,
                claimed_by=f"crashed-worker-{suffix}",
                lease_expires_at=expired_at,
            )

            exhausted_event = OutboxEvent(
                org_id=org_id,
                workspace_id=workspace_id,
                event_type=event_type,
                schema_version=1,
                aggregate_type="test",
                aggregate_id=f"exhausted-{suffix}",
                idempotency_key=f"recovery-exhausted-{suffix}",
                payload={"synthetic": True},
                status="pending",
                attempts=8,
                max_attempts=8,
            )

            setup.add_all([expired_event, exhausted_event])
            setup.flush()

            event_ids.extend([expired_event.id, exhausted_event.id])
            setup.commit()
        finally:
            setup.close()

        recovery = Session()
        try:
            requeued, dead_lettered = reconcile_outbox_events(
                recovery,
                limit=10,
            )
            recovery.commit()

            assert requeued == 1
            assert dead_lettered == 1
        finally:
            recovery.close()

        verification = Session()
        try:
            recovered = verification.query(OutboxEvent).filter(
                OutboxEvent.id == event_ids[0]
            ).one()

            dead = verification.query(OutboxEvent).filter(
                OutboxEvent.id == event_ids[1]
            ).one()

            assert recovered.status == "pending"
            assert recovered.attempts == 2
            assert recovered.claimed_by is None
            assert recovered.lease_expires_at is None

            assert dead.status == "dead_letter"
            assert dead.attempts == dead.max_attempts
            assert dead.claimed_by is None
            assert dead.lease_expires_at is None
        finally:
            verification.close()

        # Confirm that a recovered event can be claimed by a new worker.
        claimant = Session()
        try:
            claimed = claim_outbox_batch(
                claimant,
                worker_id=f"recovery-worker-{suffix}",
                event_types={event_type},
                limit=10,
            )

            assert len(claimed) == 1
            assert claimed[0].id == event_ids[0]
            assert claimed[0].attempts == 3
            assert claimed[0].idempotency_key == f"recovery-expired-{suffix}"

            claimant.commit()
        finally:
            claimant.rollback()
            claimant.close()

    finally:
        if org_id:
            cleanup = Session()
            try:
                cleanup.query(OutboxEvent).filter(
                    OutboxEvent.id.in_(event_ids)
                ).delete(synchronize_session=False)

                cleanup.query(Workspace).filter(
                    Workspace.id == workspace_id
                ).delete(synchronize_session=False)

                cleanup.query(Organization).filter(
                    Organization.id == org_id
                ).delete(synchronize_session=False)

                cleanup.commit()
            finally:
                cleanup.close()

        engine.dispose()
