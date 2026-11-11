import os
import uuid

import pytest
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
from app.worker_service import claim_next_execution


def test_postgres_workers_claim_different_executions():
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
                runtime="claude_managed_agents",
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

    finally:
        # Remove only records created by this test.
        if org_id is not None:
            cleanup = Session()
            try:
                if execution_ids:
                    cleanup.query(AuditEvent).filter(
                        AuditEvent.resource_id.in_(execution_ids)
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