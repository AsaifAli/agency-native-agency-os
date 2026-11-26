"""PostgreSQL security-boundary tests for worker lease capabilities.

These tests intentionally use the real NOBYPASSRLS agency_os_worker login.
They must not be replaced by SQLite tests: caller-controlled GUC behavior and
role/table grants are PostgreSQL authorization properties.
"""
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app.models import Agent, DataClass, Organization, Task, User, Workspace

ADMIN_URL = os.getenv("AGENCY_OS_TEST_RLS_ADMIN_DATABASE_URL")
WORKER_URL = os.getenv("AGENCY_OS_TEST_RLS_WORKER_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not (ADMIN_URL and WORKER_URL),
    reason="Set admin and worker PostgreSQL URLs for worker capability boundary tests",
)


def test_forged_workspace_gucs_do_not_authorize_worker_reads():
    """A worker with no lease capability cannot impersonate a workspace."""
    admin_engine = create_engine(ADMIN_URL, pool_pre_ping=True)
    worker_engine = create_engine(WORKER_URL, pool_size=1, max_overflow=0, pool_pre_ping=True)
    Admin = sessionmaker(bind=admin_engine, expire_on_commit=False)
    Worker = sessionmaker(bind=worker_engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:12]
    user = User(email=f"worker-capability-{suffix}@example.test")
    org = Organization(name=f"Worker capability boundary {suffix}")
    try:
        with Admin() as db:
            db.add_all([user, org])
            db.flush()
            workspace = Workspace(
                id=f"cap-ws-{suffix}", org_id=org.id, name="Capability boundary",
            )
            db.add(workspace)
            db.flush()
            agent = Agent(
                org_id=org.id, workspace_id=workspace.id,
                name=f"Capability agent {suffix}", runtime="mock",
                data_class=DataClass.synthetic, enabled=True,
            )
            task = Task(
                org_id=org.id, workspace_id=workspace.id,
                title="Must remain invisible without a lease",
                description="Synthetic security fixture", created_by=user.id,
            )
            db.add_all([agent, task])
            db.commit()
            workspace_id = workspace.id
            org_id = org.id
            task_id = task.id

        with Worker() as db:
            # The historical authorization mechanism accepts these caller-set
            # values. The capability design must make them irrelevant.
            db.execute(
                text("SELECT set_config('agency_os.machine_org_id', :org, true)"),
                {"org": org_id},
            )
            db.execute(
                text("SELECT set_config('agency_os.machine_workspace_id', :workspace, true)"),
                {"workspace": workspace_id},
            )
            visible = db.execute(
                text("SELECT id FROM public.tasks WHERE id = :task_id"),
                {"task_id": task_id},
            ).all()
            assert visible == [], (
                "Forged tenant GUCs authorized a worker read without a lease capability"
            )
            db.rollback()
    finally:
        with Admin() as db:
            db.execute(text("DELETE FROM public.tasks WHERE org_id = :org"), {"org": org.id})
            db.execute(text("DELETE FROM public.agents WHERE org_id = :org"), {"org": org.id})
            db.execute(text("DELETE FROM public.workspaces WHERE org_id = :org"), {"org": org.id})
            db.execute(text("DELETE FROM public.organizations WHERE id = :org"), {"org": org.id})
            db.execute(text("DELETE FROM public.users WHERE id = :user"), {"user": user.id})
            db.commit()
        worker_engine.dispose()
        admin_engine.dispose()


def test_worker_cannot_read_private_lease_capability_storage():
    """Lease hashes and transaction context must never be readable by workers."""
    admin_engine = create_engine(ADMIN_URL, pool_pre_ping=True)
    worker_engine = create_engine(WORKER_URL, pool_pre_ping=True)
    try:
        with admin_engine.connect() as connection:
            exists = connection.execute(
                text("SELECT to_regclass('agency_os_private.worker_lease_capabilities')")
            ).scalar_one()
            assert exists is not None, "Capability storage must exist before privilege testing"

        with worker_engine.connect() as connection:
            has_select = connection.execute(
                text(
                    "SELECT has_table_privilege(current_user, "
                    "'agency_os_private.worker_lease_capabilities', 'SELECT')"
                )
            ).scalar_one()
            assert has_select is False
            with pytest.raises(DBAPIError):
                connection.execute(
                    text("SELECT * FROM agency_os_private.worker_lease_capabilities LIMIT 1")
                ).all()
    finally:
        worker_engine.dispose()
        admin_engine.dispose()


def test_worker_can_only_establish_context_through_capability_verifier():
    """The worker may invoke the verifier but cannot forge its private context."""
    admin_engine = create_engine(ADMIN_URL, pool_pre_ping=True)
    worker_engine = create_engine(WORKER_URL, pool_pre_ping=True)
    try:
        with admin_engine.connect() as connection:
            function_exists = connection.execute(
                text("""
                    SELECT to_regprocedure(
                        'agency_os_private.establish_worker_execution_context(bytea,text,text,text,integer)'
                    )
                """)
            ).scalar_one()
            assert function_exists is not None, "Capability verifier must be installed"

        with worker_engine.connect() as connection:
            can_execute = connection.execute(
                text("""
                    SELECT has_function_privilege(
                        current_user,
                        'agency_os_private.establish_worker_execution_context(bytea,text,text,text,integer)',
                        'EXECUTE'
                    )
                """)
            ).scalar_one()
            can_insert_context = connection.execute(
                text("""
                    SELECT has_table_privilege(
                        current_user,
                        'agency_os_private.worker_transaction_context',
                        'INSERT'
                    )
                """)
            ).scalar_one()
            assert can_execute is True
            assert can_insert_context is False

            accepted = connection.execute(
                text("""
                    SELECT agency_os_private.establish_worker_execution_context(
                        decode(repeat('00', 32), 'hex'),
                        'nonexistent-execution',
                        'nonexistent-attempt',
                        'untrusted-worker',
                        1
                    )
                """)
            ).scalar_one()
            assert accepted is False
            connection.rollback()
    finally:
        worker_engine.dispose()
        admin_engine.dispose()
