"""PostgreSQL-only concurrency tests for single-use founder approvals.

These tests use the isolated disposable agency_os_worker_test database. Each
competing request has its own SQLAlchemy session and transaction.
"""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import os
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.action_policy import require_approved_action
from app.models import (
    Approval,
    ApprovalStatus,
    AuditEvent,
    FounderAuthority,
    Membership,
    Organization,
    Role,
    Task,
    User,
    Workspace,
)


def test_postgres_approval_is_consumed_once_with_protected_action_in_transaction():
    database_url = os.getenv("AGENCY_OS_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set AGENCY_OS_TEST_DATABASE_URL for PostgreSQL approval concurrency test")

    parsed_url = make_url(database_url)
    assert parsed_url.get_backend_name() == "postgresql"
    assert parsed_url.database == "agency_os_worker_test", (
        "Safety check: this test may only use agency_os_worker_test"
    )

    engine = create_engine(database_url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:12]
    org_id = workspace_id = task_id = approval_id = None

    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT current_database()").scalar_one() == "agency_os_worker_test"
            assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()

        setup = Session()
        try:
            founder = User(email=f"approval-founder-{suffix}@test.local")
            actor = User(email=f"approval-actor-{suffix}@test.local")
            org = Organization(name=f"Approval Concurrency {suffix}")
            setup.add_all([founder, actor, org])
            setup.flush()

            workspace = Workspace(
                id=f"approval-ws-{suffix}",
                org_id=org.id,
                name="Approval concurrency workspace",
            )
            setup.add(workspace)
            setup.flush()

            setup.add_all([
                Membership(org_id=org.id, user_id=founder.id, role=Role.owner),
                Membership(org_id=org.id, user_id=actor.id, role=Role.operator),
                FounderAuthority(
                    org_id=org.id,
                    user_id=founder.id,
                    grant_source="postgres_test",
                ),
            ])
            task = Task(
                org_id=org.id,
                workspace_id=workspace.id,
                title="Protected release action",
                description="Synthetic PostgreSQL approval concurrency test",
                created_by=actor.id,
                status="awaiting_release",
            )
            setup.add(task)
            setup.flush()

            approval = Approval(
                org_id=org.id,
                workspace_id=workspace.id,
                action_type="production.release",
                idempotency_key=f"approval-concurrency-{suffix}",
                resource_id=task.id,
                request_payload={"synthetic": True},
                status=ApprovalStatus.approved,
                requested_by=actor.id,
                decided_by=founder.id,
            )
            setup.add(approval)
            setup.flush()
            org_id, workspace_id, task_id, approval_id = (
                org.id, workspace.id, task.id, approval.id
            )
            founder_id, actor_id = founder.id, actor.id
            setup.commit()
        finally:
            setup.close()

        barrier = Barrier(2)

        def consume_and_apply():
            session = Session()
            try:
                barrier.wait(timeout=10)
                require_approved_action(
                    session,
                    approval_id=approval_id,
                    org_id=org_id,
                    workspace_id=workspace_id,
                    action_type="production.release",
                    resource_id=task_id,
                    actor_user_id=actor_id,
                )
                # This mutation deliberately shares the approval-consumption
                # transaction. A failed/rolled-back approval must not release it.
                task = session.query(Task).filter_by(
                    id=task_id,
                    org_id=org_id,
                    workspace_id=workspace_id,
                ).one()
                task.status = "released"
                session.commit()
                return "committed"
            except HTTPException as exc:
                session.rollback()
                return f"http_{exc.status_code}"
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _index: consume_and_apply(), range(2)))

        assert sorted(outcomes) == ["committed", "http_409"]

        verification = Session()
        try:
            stored_approval = verification.query(Approval).filter_by(id=approval_id).one()
            protected_task = verification.query(Task).filter_by(id=task_id).one()
            consumed_events = verification.query(AuditEvent).filter_by(
                org_id=org_id,
                event_type="approval.consumed",
                resource_id=approval_id,
            ).all()

            assert stored_approval.consumed_at is not None
            assert stored_approval.consumed_by == actor_id
            assert protected_task.status == "released"
            assert len(consumed_events) == 1
            assert consumed_events[0].actor_user_id == actor_id
        finally:
            verification.close()

    finally:
        if org_id is not None:
            cleanup = Session()
            try:
                cleanup.query(AuditEvent).filter(
                    AuditEvent.org_id == org_id
                ).delete(synchronize_session=False)
                if approval_id:
                    cleanup.query(Approval).filter(
                        Approval.id == approval_id
                    ).delete(synchronize_session=False)
                if task_id:
                    cleanup.query(Task).filter(Task.id == task_id).delete(
                        synchronize_session=False
                    )
                cleanup.query(FounderAuthority).filter(
                    FounderAuthority.org_id == org_id
                ).delete(synchronize_session=False)
                cleanup.query(Membership).filter(
                    Membership.org_id == org_id
                ).delete(synchronize_session=False)
                if workspace_id:
                    cleanup.query(Workspace).filter(
                        Workspace.id == workspace_id
                    ).delete(synchronize_session=False)
                cleanup.query(User).filter(
                    User.email.in_([
                        f"approval-founder-{suffix}@test.local",
                        f"approval-actor-{suffix}@test.local",
                    ])
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
