"""PostgreSQL lease/control race regression tests.

Uses only the disposable agency_os_worker_test database configured by the
isolated postgres-test compose stack.
"""
from datetime import datetime, timedelta, timezone
import os
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.execution_controls import acknowledge_execution_cancel
from app.models import (
    Agent, AuditEvent, DataClass, Execution, ExecutionAttempt,
    ExecutionAttemptStatus, ExecutionStatus, Organization, Task, User, Workspace,
)
from app.worker_service import recover_expired_execution_leases


def test_expired_worker_cannot_acknowledge_cancel_after_lease_recovery():
    database_url = os.getenv("AGENCY_OS_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set AGENCY_OS_TEST_DATABASE_URL for PostgreSQL control race test")

    parsed_url = make_url(database_url)
    assert parsed_url.get_backend_name() == "postgresql"
    assert parsed_url.database == "agency_os_worker_test", (
        "Safety check: this test may only use agency_os_worker_test"
    )

    engine = create_engine(database_url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:12]
    org_id = workspace_id = execution_id = attempt_id = None

    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql(
                "SELECT current_database()"
            ).scalar_one() == "agency_os_worker_test"
            assert connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one()

        setup = Session()
        try:
            user = User(email=f"control-race-{suffix}@test.local")
            org = Organization(name=f"Control Race {suffix}")
            setup.add_all([user, org])
            setup.flush()
            workspace = Workspace(
                id=f"control-race-{suffix}", org_id=org.id,
                name="Control race workspace",
            )
            setup.add(workspace)
            setup.flush()
            agent = Agent(
                org_id=org.id, workspace_id=workspace.id,
                name=f"Control race agent {suffix}", runtime="claude_managed_agents",
                data_class=DataClass.synthetic, enabled=True,
            )
            task = Task(
                org_id=org.id, workspace_id=workspace.id,
                title="Control race task", created_by=user.id,
            )
            setup.add_all([agent, task])
            setup.flush()
            execution = Execution(
                org_id=org.id, workspace_id=workspace.id, task_id=task.id,
                agent_id=agent.id, requested_by=user.id,
                idempotency_key=f"control-race-{suffix}",
                runtime="claude_managed_agents", data_class=DataClass.synthetic,
                status=ExecutionStatus.running, attempt_count=1, max_attempts=3,
                request_metadata={
                    "control_request": {
                        "action": "cancel",
                        "requested_at": datetime.now(timezone.utc).isoformat(),
                        "requested_by": user.id,
                    }
                },
            )
            setup.add(execution)
            setup.flush()
            attempt = ExecutionAttempt(
                execution_id=execution.id, attempt_number=1,
                worker_id=f"stale-worker-{suffix}", runtime=execution.runtime,
                status=ExecutionAttemptStatus.running,
                lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=10),
                heartbeat_at=datetime.now(timezone.utc) - timedelta(minutes=2),
            )
            setup.add(attempt)
            setup.flush()
            org_id, workspace_id = org.id, workspace.id
            execution_id, attempt_id, worker_id = execution.id, attempt.id, attempt.worker_id
            setup.commit()
        finally:
            setup.close()

        recovery = Session()
        try:
            recovered_count = recover_expired_execution_leases(
                recovery, base_delay_seconds=5, max_delay_seconds=30
            )
            # The recovery service scans all workspaces; the shared test DB can
            # contain other expired synthetic leases. The test below verifies
            # this execution's attempt was actually abandoned.
            assert recovered_count >= 1
            recovery.commit()
        finally:
            recovery.close()

        stale_worker = Session()
        try:
            from app.worker_service import InvalidExecutionState
            # Recovery clears the lease; a stale acknowledgement is therefore
            # rejected as an invalid state (rather than an unexpired lease timeout).
            with pytest.raises(InvalidExecutionState):
                acknowledge_execution_cancel(
                    stale_worker, execution_id=execution_id,
                    attempt_id=attempt_id, worker_id=worker_id,
                )
            stale_worker.rollback()
        finally:
            stale_worker.close()

        verify = Session()
        try:
            execution = verify.query(Execution).filter_by(id=execution_id).one()
            attempt = verify.query(ExecutionAttempt).filter_by(id=attempt_id).one()
            assert execution.status == ExecutionStatus.retry_wait
            assert execution.finished_at is None
            assert attempt.status == ExecutionAttemptStatus.abandoned
            assert attempt.lease_expires_at is None
            assert verify.query(AuditEvent).filter_by(
                org_id=org_id, resource_id=execution_id,
                event_type="execution.cancelled",
            ).count() == 0
            assert verify.query(AuditEvent).filter_by(
                org_id=org_id, resource_id=attempt_id,
                event_type="execution.attempt_abandoned",
            ).count() == 1
        finally:
            verify.close()
    finally:
        if org_id is not None:
            cleanup = Session()
            try:
                cleanup.query(AuditEvent).filter(
                    AuditEvent.org_id == org_id
                ).delete(synchronize_session=False)
                if attempt_id:
                    cleanup.query(ExecutionAttempt).filter(
                        ExecutionAttempt.id == attempt_id
                    ).delete(synchronize_session=False)
                if execution_id:
                    cleanup.query(Execution).filter(
                        Execution.id == execution_id
                    ).delete(synchronize_session=False)
                cleanup.query(Task).filter(
                    Task.org_id == org_id
                ).delete(synchronize_session=False)
                cleanup.query(Agent).filter(
                    Agent.org_id == org_id
                ).delete(synchronize_session=False)
                if workspace_id:
                    cleanup.query(Workspace).filter(
                        Workspace.id == workspace_id
                    ).delete(synchronize_session=False)
                cleanup.query(User).filter(
                    User.email == f"control-race-{suffix}@test.local"
                ).delete(synchronize_session=False)
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
