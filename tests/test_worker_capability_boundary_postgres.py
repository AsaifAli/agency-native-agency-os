"""PostgreSQL security-boundary tests for worker lease capabilities.

These tests intentionally use the real NOBYPASSRLS agency_os_worker login.
They must not be replaced by SQLite tests: caller-controlled GUC behavior and
role/table grants are PostgreSQL authorization properties.
"""
import os
import hashlib
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app.execution_service import create_execution
from app.config import settings
from app.models import Execution, ExecutionAttempt, AuditEvent
from app.security_models import MachineIdentity
from app.worker.processor import process_one_execution
from app.db import (
    scoped_worker_capability_session_factory,
    scoped_worker_workspace_session_factory,
)
from app.worker_service import (
    claim_worker_execution_capability, claim_worker_maintenance_scope,
    heartbeat_execution,
)
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
            has_workspace_select = connection.execute(
                text(
                    "SELECT has_table_privilege(current_user, "
                    "'agency_os_private.worker_workspace_capabilities', 'SELECT')"
                )
            ).scalar_one()
            assert has_workspace_select is False
            identity_write_privileges = connection.execute(text("""
                SELECT
                    has_table_privilege(current_user, 'public.machine_identities', 'INSERT'),
                    has_table_privilege(current_user, 'public.machine_identities', 'UPDATE'),
                    has_table_privilege(current_user, 'public.machine_identities', 'DELETE'),
                    has_column_privilege(current_user, 'public.machine_identities', 'last_used_at', 'UPDATE')
            """)).one()
            assert tuple(identity_write_privileges) == (False, False, False, True)
            with pytest.raises(DBAPIError):
                connection.execute(
                    text("SELECT * FROM agency_os_private.worker_lease_capabilities LIMIT 1")
                ).all()
            connection.rollback()
            with pytest.raises(DBAPIError):
                connection.execute(
                    text("SELECT * FROM agency_os_private.worker_workspace_capabilities LIMIT 1")
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
            can_enumerate = connection.execute(
                text("""
                    SELECT has_function_privilege(
                        current_user,
                        'agency_os_private.worker_workspace_scopes()',
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
            assert can_enumerate is False

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


def test_worker_claim_rpc_issues_a_live_workspace_bound_capability():
    """A worker can claim one execution, but cannot read another workspace."""
    admin_engine = create_engine(ADMIN_URL, pool_pre_ping=True)
    worker_engine = create_engine(WORKER_URL, pool_pre_ping=True)
    Admin = sessionmaker(bind=admin_engine, expire_on_commit=False)
    Worker = sessionmaker(bind=worker_engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:12]
    user = User(email=f"worker-claim-{suffix}@example.test")
    org = Organization(name=f"Worker claim {suffix}")
    try:
        with Admin() as db:
            db.add_all([user, org])
            db.flush()
            workspace_a = Workspace(id=f"00000000-0000-4000-8000-{suffix}", org_id=org.id, name="A")
            workspace_b = Workspace(id=f"00000000-0000-4000-8001-{suffix}", org_id=org.id, name="B")
            db.add_all([workspace_a, workspace_b])
            db.flush()
            agent = Agent(
                org_id=org.id, workspace_id=workspace_a.id,
                name=f"Claim agent {suffix}", runtime="mock",
                data_class=DataClass.synthetic, enabled=True,
            )
            agent_b = Agent(
                org_id=org.id, workspace_id=workspace_b.id,
                name=f"Other agent {suffix}", runtime="mock",
                data_class=DataClass.synthetic, enabled=True,
            )
            task_a = Task(
                org_id=org.id, workspace_id=workspace_a.id,
                title="Claimable task", description="Synthetic", created_by=user.id,
            )
            task_b = Task(
                org_id=org.id, workspace_id=workspace_b.id,
                title="Must remain hidden", description="Synthetic", created_by=user.id,
            )
            db.add_all([agent, agent_b, task_a, task_b])
            db.flush()
            identity_a = MachineIdentity(
                org_id=org.id, workspace_id=workspace_a.id,
                name=f"Agent identity A {suffix}", subject_type="agent",
                subject_id=agent.id, token_hash=hashlib.sha256(f"{suffix}-identity-a".encode()).hexdigest(), token_prefix="aos_mi_a",
                scopes=["sessions:create", "tools:invoke", "tool:sample"],
                allowed_data_classes=["synthetic"],
                expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
                created_by_user_id=user.id,
            )
            identity_b = MachineIdentity(
                org_id=org.id, workspace_id=workspace_b.id,
                name=f"Agent identity B {suffix}", subject_type="agent",
                subject_id=agent_b.id, token_hash=hashlib.sha256(f"{suffix}-identity-b".encode()).hexdigest(), token_prefix="aos_mi_b",
                scopes=["sessions:create", "tools:invoke", "tool:sample"],
                allowed_data_classes=["synthetic"],
                expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
                created_by_user_id=user.id,
            )
            db.add_all([identity_a, identity_b])
            db.flush()
            identity_a_id = identity_a.id
            execution = create_execution(
                db, org_id=org.id, workspace_id=workspace_a.id,
                task_id=task_a.id, agent_id=agent.id, requested_by=user.id,
                idempotency_key=f"worker-capability-{suffix}",
            )
            execution.queued_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
            execution_id, task_a_id, task_b_id = execution.id, task_a.id, task_b.id
            workspace_a_id, workspace_b_id = workspace_a.id, workspace_b.id
            db.commit()

        worker_id = f"capability-worker-{suffix}"
        with Worker() as claim_db:
            capability = claim_worker_execution_capability(
                claim_db, worker_id=worker_id, lease_seconds=60,
            )
            assert capability is not None
            assert capability.execution_id == execution_id
            claim_db.commit()

        scoped_factory = scoped_worker_capability_session_factory(capability, Worker)
        with scoped_factory() as db:
            visible_execution = db.execute(
                text("SELECT id FROM public.executions WHERE id = :id"),
                {"id": execution_id},
            ).scalars().all()
            visible_task_a = db.execute(
                text("SELECT id FROM public.tasks WHERE id = :id"),
                {"id": task_a_id},
            ).scalars().all()
            visible_task_b = db.execute(
                text("SELECT id FROM public.tasks WHERE id = :id"),
                {"id": task_b_id},
            ).scalars().all()
            assert visible_execution == [execution_id]
            assert visible_task_a == [task_a_id]
            assert visible_task_b == []
            visible_identities = db.query(MachineIdentity.id).all()
            assert [row[0] for row in visible_identities] == [identity_a_id]
            db.execute(text("""
                UPDATE public.machine_identities
                SET last_used_at = clock_timestamp()
                WHERE id = :identity_id
            """), {"identity_id": identity_a_id})
            db.commit()

        with scoped_factory() as db:
            with pytest.raises(DBAPIError):
                db.execute(text("""
                    UPDATE public.machine_identities
                    SET scopes = '["*"]'::json
                    WHERE id = :identity_id
                """), {"identity_id": identity_a_id})
            db.rollback()

        # A fresh transaction on the same capability-bearing factory must
        # establish a new transaction-bound context, not reuse the old PID/xid.
        with scoped_factory() as db:
            assert db.execute(
                text("SELECT id FROM public.tasks WHERE id = :id"),
                {"id": task_a_id},
            ).scalars().all() == [task_a_id]
            heartbeat_execution(
                db, execution_id=capability.execution_id,
                attempt_id=capability.attempt_id, worker_id=worker_id,
                lease_seconds=60,
            )
            renewed = db.execute(text(
                "SELECT agency_os_private.renew_worker_execution_capability()"
            )).scalar_one()
            assert renewed is True
            db.commit()

        with scoped_factory() as db:
            assert db.execute(
                text("SELECT id FROM public.tasks WHERE id = :id"),
                {"id": task_a_id},
            ).scalars().all() == [task_a_id]
            db.rollback()

        # An expired capability cannot establish a new transaction context.
        with Admin() as db:
            db.execute(
                text("""
                    UPDATE agency_os_private.worker_lease_capabilities
                    SET expires_at = clock_timestamp() - interval '1 second'
                    WHERE token_hash = :token_hash
                """),
                {"token_hash": hashlib.sha256(capability.token).digest()},
            )
            db.commit()
        with scoped_factory() as db:
            with pytest.raises(PermissionError, match="execution capability"):
                db.execute(text("SELECT id FROM public.tasks LIMIT 1")).all()

        # Maintenance gets a separate, bounded workspace capability. It can
        # access only the database-selected workspace and is explicitly released.
        with Worker() as scope_claim_db:
            workspace_capability = claim_worker_maintenance_scope(
                scope_claim_db, worker_id=worker_id, lease_seconds=120,
            )
            assert workspace_capability is not None
            # Maintenance claims are global and ordered across every workspace
            # in the disposable database, not scoped to this test's organization.
            # Assert the returned capability is the sole visible workspace rather
            # than assuming this fixture is the first workspace in the database.
            scope_claim_db.commit()

        workspace_factory = scoped_worker_workspace_session_factory(
            workspace_capability, Worker,
        )
        with workspace_factory() as db:
            visible_workspaces = db.execute(
                text("SELECT id FROM public.workspaces")
            ).scalars().all()
            assert visible_workspaces == [workspace_capability.workspace_id]

            visible_fixture_tasks = db.execute(
                text("""
                    SELECT id FROM public.tasks
                    WHERE id IN (:task_a_id, :task_b_id)
                    ORDER BY id
                """),
                {"task_a_id": task_a_id, "task_b_id": task_b_id},
            ).scalars().all()
            expected_fixture_tasks = (
                [task_a_id] if workspace_capability.workspace_id == workspace_a_id
                else [task_b_id] if workspace_capability.workspace_id == workspace_b_id
                else []
            )
            assert visible_fixture_tasks == expected_fixture_tasks

            # Workspace maintenance cannot inspect machine identities; that
            # access is reserved for an execution capability bound to its agent.
            assert db.query(MachineIdentity.id).all() == []
            renewed = db.execute(text(
                "SELECT agency_os_private.renew_worker_maintenance_scope(:lease_seconds)"
            ), {"lease_seconds": workspace_capability.lease_seconds}).scalar_one()
            assert renewed is True
            released = db.execute(text(
                "SELECT agency_os_private.release_worker_maintenance_scope()"
            )).scalar_one()
            assert released is True
            db.commit()

        with workspace_factory() as db:
            with pytest.raises(PermissionError, match="maintenance capability"):
                db.execute(text("SELECT id FROM public.tasks LIMIT 1")).all()
    finally:
        with Admin() as db:
            db.execute(text("DELETE FROM public.audit_events WHERE org_id = :org"), {"org": org.id})
            db.execute(text("""
                DELETE FROM public.execution_attempts
                WHERE execution_id IN (
                    SELECT id FROM public.executions WHERE org_id = :org
                )
            """), {"org": org.id})
            db.execute(text("DELETE FROM public.executions WHERE org_id = :org"), {"org": org.id})
            db.execute(text("DELETE FROM public.machine_identities WHERE org_id = :org"), {"org": org.id})
            db.execute(text("DELETE FROM public.tasks WHERE org_id = :org"), {"org": org.id})
            db.execute(text("DELETE FROM public.agents WHERE org_id = :org"), {"org": org.id})
            db.execute(text("DELETE FROM public.workspaces WHERE org_id = :org"), {"org": org.id})
            db.execute(text("DELETE FROM public.organizations WHERE id = :org"), {"org": org.id})
            db.execute(text("DELETE FROM public.users WHERE id = :user"), {"user": user.id})
            db.commit()
        worker_engine.dispose()
        admin_engine.dispose()


def test_worker_processor_completes_execution_end_to_end_with_capability(monkeypatch):
    """The real worker role can claim, run, and persist completion under RLS."""
    admin_engine = create_engine(ADMIN_URL, pool_pre_ping=True)
    worker_engine = create_engine(WORKER_URL, pool_pre_ping=True)
    Admin = sessionmaker(bind=admin_engine, expire_on_commit=False)
    Worker = sessionmaker(bind=worker_engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:12]
    user = User(email=f"worker-e2e-{suffix}@example.test")
    org = Organization(name=f"Worker E2E {suffix}")
    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(settings, "mock_runtime_enabled", True)
    try:
        with Admin() as db:
            db.add_all([user, org])
            db.flush()
            workspace = Workspace(
                id=f"worker-e2e-{suffix}", org_id=org.id, name="E2E workspace",
            )
            db.add(workspace)
            db.flush()
            agent = Agent(
                org_id=org.id, workspace_id=workspace.id,
                name=f"E2E agent {suffix}", runtime="mock",
                data_class=DataClass.synthetic, enabled=True,
            )
            task = Task(
                org_id=org.id, workspace_id=workspace.id,
                title="Capability E2E task", description="Synthetic only",
                created_by=user.id,
            )
            db.add_all([agent, task])
            db.flush()
            execution = create_execution(
                db, org_id=org.id, workspace_id=workspace.id,
                task_id=task.id, agent_id=agent.id, requested_by=user.id,
                idempotency_key=f"worker-e2e-{suffix}",
            )
            execution.queued_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
            execution_id = execution.id
            db.commit()

        result = process_one_execution(
            worker_id=f"worker-e2e-{suffix}", lease_seconds=60,
            session_factory=Worker,
        )
        assert result == execution_id

        with Admin() as db:
            persisted = db.query(Execution).filter_by(id=execution_id).one()
            attempt = db.query(ExecutionAttempt).filter_by(execution_id=execution_id).one()
            events = db.query(AuditEvent).filter_by(
                resource_type="execution", resource_id=execution_id,
            ).all()
            assert persisted.status.value == "succeeded"
            assert attempt.status.value == "succeeded"
            assert persisted.result["provider"] == "mock"
            assert any(event.event_type == "execution.succeeded" for event in events)
            capability_state = db.execute(text("""
                SELECT invalidated_at
                FROM agency_os_private.worker_lease_capabilities
                WHERE execution_id = :execution_id
            """), {"execution_id": execution_id}).scalar_one()
            assert capability_state is not None, "Terminal execution must revoke its capability"
    finally:
        with Admin() as db:
            db.execute(text("DELETE FROM public.audit_events WHERE org_id = :org"), {"org": org.id})
            db.execute(text("""
                DELETE FROM public.execution_attempts
                WHERE execution_id IN (
                    SELECT id FROM public.executions WHERE org_id = :org
                )
            """), {"org": org.id})
            db.execute(text("DELETE FROM public.executions WHERE org_id = :org"), {"org": org.id})
            db.execute(text("DELETE FROM public.tasks WHERE org_id = :org"), {"org": org.id})
            db.execute(text("DELETE FROM public.agents WHERE org_id = :org"), {"org": org.id})
            db.execute(text("DELETE FROM public.workspaces WHERE org_id = :org"), {"org": org.id})
            db.execute(text("DELETE FROM public.organizations WHERE id = :org"), {"org": org.id})
            db.execute(text("DELETE FROM public.users WHERE id = :user"), {"user": user.id})
            db.commit()
        worker_engine.dispose()
        admin_engine.dispose()


def test_worker_public_table_grants_are_least_privilege():
    """Worker role has only the table operations required by its runtime paths."""
    expected_select = {
        "agent_sessions", "agents", "delegations", "execution_attempts",
        "executions", "lead_research_drafts", "machine_identities",
        "orchestration_plan_drafts", "outbox_events", "tasks",
        "tool_invocations", "workforce_capabilities", "workforce_members",
        "workspaces",
    }
    expected_insert = {
        "agent_sessions", "audit_events", "executions",
        "lead_research_drafts", "tool_invocations",
    }
    expected_update = {
        "agent_sessions", "delegations", "execution_attempts",
        "executions", "orchestration_plan_drafts", "outbox_events",
        "tasks", "tool_invocations", "workforce_capabilities", "workforce_members",
    }

    worker_engine = create_engine(WORKER_URL, pool_pre_ping=True)
    try:
        with worker_engine.connect() as connection:
            rows = connection.execute(text("""
                SELECT
                    c.relname,
                    has_table_privilege(current_user, c.oid, 'SELECT') AS can_select,
                    has_table_privilege(current_user, c.oid, 'INSERT') AS can_insert,
                    has_table_privilege(current_user, c.oid, 'UPDATE') AS can_update,
                    has_table_privilege(current_user, c.oid, 'DELETE') AS can_delete
                FROM pg_class AS c
                JOIN pg_namespace AS n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
            """)).mappings().all()

            actual_select = {row["relname"] for row in rows if row["can_select"]}
            actual_insert = {row["relname"] for row in rows if row["can_insert"]}
            actual_update = {row["relname"] for row in rows if row["can_update"]}
            actual_delete = {row["relname"] for row in rows if row["can_delete"]}

            assert actual_select == expected_select
            assert actual_insert == expected_insert
            assert actual_update == expected_update
            assert actual_delete == set()

            assert connection.execute(text("""
                SELECT has_column_privilege(
                    current_user, 'public.machine_identities',
                    'last_used_at', 'UPDATE'
                )
            """)).scalar_one() is True
            assert connection.execute(text("""
                SELECT has_column_privilege(
                    current_user, 'public.machine_identities',
                    'revoked_at', 'UPDATE'
                )
            """)).scalar_one() is False
    finally:
        worker_engine.dispose()
