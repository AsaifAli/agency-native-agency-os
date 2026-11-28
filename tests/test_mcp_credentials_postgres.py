"""PostgreSQL integration tests for the MCP session credential privilege boundary."""
import hashlib
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app.models import Agent, DataClass, Execution, ExecutionStatus, Organization, Task, User, Workspace
from app.security_models import AgentSession, MachineIdentity, MachineSessionCredential

ADMIN_URL = os.getenv("AGENCY_OS_TEST_RLS_ADMIN_DATABASE_URL")
APP_URL = os.getenv("AGENCY_OS_TEST_RLS_DATABASE_URL")
WORKER_URL = os.getenv("AGENCY_OS_TEST_RLS_WORKER_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not (ADMIN_URL and APP_URL and WORKER_URL),
    reason="Dedicated admin, app and worker PostgreSQL URLs are required",
)


def test_mcp_credential_hash_is_not_readable_and_auth_is_database_owned():
    admin_engine = create_engine(ADMIN_URL, pool_pre_ping=True)
    app_engine = create_engine(APP_URL, pool_pre_ping=True)
    worker_engine = create_engine(WORKER_URL, pool_pre_ping=True)
    Admin = sessionmaker(bind=admin_engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:12]
    user = User(email=f"mcp-credential-{suffix}@example.test")
    org = Organization(name=f"MCP credential boundary {suffix}")
    now = datetime.now(timezone.utc)
    secret = "mcp-test-secret-" + uuid.uuid4().hex
    token_hash = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    credential_id = str(uuid.uuid4())
    try:
        with Admin() as db:
            db.add_all([user, org])
            db.flush()
            workspace = Workspace(id=f"mcp-ws-{suffix}", org_id=org.id, name="MCP credential workspace")
            db.add(workspace)
            db.flush()
            agent = Agent(
                id=f"mcp-agent-{suffix}", org_id=org.id, workspace_id=workspace.id,
                name="MCP test agent", department="Engineering",
                instructions="Synthetic test only.", runtime="claude_managed_agents",
                data_class=DataClass.public, enabled=True,
            )
            db.add(agent)
            db.flush()
            identity = MachineIdentity(
                id=f"mcp-mi-{suffix}", org_id=org.id, workspace_id=workspace.id,
                name="MCP test identity", subject_type="agent", subject_id=agent.id,
                token_hash=hashlib.sha256(f"identity-{suffix}".encode()).hexdigest(),
                token_prefix="aos_mi_test", scopes=["sessions:create", "tools:invoke"],
                allowed_data_classes=["public"], expires_at=now + timedelta(hours=2),
                created_by_user_id=user.id,
            )
            db.add(identity)
            db.flush()
            session = AgentSession(
                id=f"mcp-session-{suffix}", org_id=org.id, workspace_id=workspace.id,
                machine_identity_id=identity.id, purpose="MCP credential boundary test",
                data_class="public", status="active", created_at=now, last_seen_at=now,
                expires_at=now + timedelta(hours=1),
            )
            db.add(session)
            db.flush()
            task = Task(
                id=f"mcp-task-{suffix}", org_id=org.id, workspace_id=workspace.id,
                title="MCP credential boundary test", created_by=user.id,
            )
            db.add(task)
            db.flush()
            execution = Execution(
                id=f"mcp-exec-{suffix}", org_id=org.id, workspace_id=workspace.id,
                task_id=task.id, agent_id=agent.id, requested_by=user.id,
                idempotency_key=f"mcp-credential-{suffix}", runtime="claude_managed_agents",
                data_class=DataClass.public, status=ExecutionStatus.running,
                machine_session_id=session.id,
            )
            db.add(execution)
            db.flush()
            credential = MachineSessionCredential(
                id=credential_id, org_id=org.id, workspace_id=workspace.id,
                machine_identity_id=identity.id, session_id=session.id,
                token_hash=token_hash, token_prefix="aos_ms_test.",
                credential_version=1, expires_at=now + timedelta(minutes=30),
                request_window_started_at=now, request_count_window=0,
            )
            db.add(credential)
            db.commit()
            expected = (org.id, workspace.id, identity.id, session.id)
            joined = db.execute(text("""
                SELECT cred.id, cred.token_hash, cred.revoked_at, cred.expires_at,
                       mi.revoked_at, mi.expires_at, s.status, s.expires_at,
                       s.data_class::text, e.status::text, e.machine_session_id
                FROM public.machine_session_credentials AS cred
                JOIN public.machine_identities AS mi
                  ON mi.id = cred.machine_identity_id
                 AND mi.org_id = cred.org_id
                 AND mi.workspace_id = cred.workspace_id
                JOIN public.agent_sessions AS s
                  ON s.id = cred.session_id
                 AND s.org_id = cred.org_id
                 AND s.workspace_id = cred.workspace_id
                 AND s.machine_identity_id = mi.id
                JOIN public.executions AS e
                  ON e.org_id = cred.org_id
                 AND e.workspace_id = cred.workspace_id
                 AND e.machine_session_id = cred.session_id
                 AND e.status::text = 'running'
                WHERE cred.id = :credential_id
            """), {"credential_id": credential_id}).first()
            assert joined is not None, "MCP auth test fixture must satisfy the live execution join"
            assert joined[1] == token_hash and joined[2] is None and joined[3] > now
            assert joined[4] is None and joined[5] > now
            assert joined[6] == "active" and joined[7] > now
            assert joined[8] in {"synthetic", "public"}
            assert joined[9] == "running" and joined[10] == session.id

        with app_engine.connect() as connection:
            assert connection.execute(text("""
                SELECT has_table_privilege(current_user, 'public.machine_session_credentials', 'SELECT'),
                       has_function_privilege(current_user,
                         'agency_os_private.authenticate_mcp_session_credential(text,text,integer)', 'EXECUTE'),
                       has_function_privilege(current_user,
                         'agency_os_private.is_mcp_session_credential_active(text,text,text,text,text,text)', 'EXECUTE')
            """)).one() == (False, True, True)
            with pytest.raises(DBAPIError):
                connection.execute(text("SELECT token_hash FROM public.machine_session_credentials")).all()
            connection.rollback()

            auth = connection.execute(text("""
                SELECT auth_status, org_id, workspace_id, machine_identity_id, session_id, credential_id
                FROM agency_os_private.authenticate_mcp_session_credential(:id, :digest, 120)
            """), {"id": credential_id, "digest": token_hash}).one()
            assert tuple(auth) == ("ok", *expected, credential_id)
            active = connection.execute(text("""
                SELECT agency_os_private.is_mcp_session_credential_active(
                    :id, :digest, :org, :workspace, :identity, :session
                )
            """), {
                "id": credential_id, "digest": token_hash, "org": expected[0],
                "workspace": expected[1], "identity": expected[2], "session": expected[3],
            }).scalar_one()
            assert active is True
            # The SECURITY DEFINER authentication functions lock the credential,
            # identity, session and execution rows. Release those locks before
            # changing execution state through the separate admin connection.
            connection.commit()

            with Admin() as db:
                db.query(Execution).filter_by(id=f"mcp-exec-{suffix}").update(
                    {"status": ExecutionStatus.paused}
                )
                db.commit()
            paused_active = connection.execute(text("""
                SELECT agency_os_private.is_mcp_session_credential_active(
                    :id, :digest, :org, :workspace, :identity, :session
                )
            """), {
                "id": credential_id, "digest": token_hash, "org": expected[0],
                "workspace": expected[1], "identity": expected[2], "session": expected[3],
            }).scalar_one()
            assert paused_active is False
            paused_auth = connection.execute(text("""
                SELECT * FROM agency_os_private.authenticate_mcp_session_credential(
                    :id, :digest, 120
                )
            """), {"id": credential_id, "digest": token_hash}).all()
            assert paused_auth == []
            with Admin() as db:
                db.query(Execution).filter_by(id=f"mcp-exec-{suffix}").update(
                    {"status": ExecutionStatus.running}
                )
                db.commit()

            invalid = connection.execute(text("""
                SELECT auth_status FROM agency_os_private.authenticate_mcp_session_credential(
                    :id, :digest, 120
                )
            """), {"id": credential_id, "digest": "0" * 64}).first()
            assert invalid is None
            connection.commit()

        with worker_engine.connect() as connection:
            privileges = connection.execute(text("""
                SELECT has_table_privilege(current_user, 'public.machine_session_credentials', 'SELECT'),
                       has_table_privilege(current_user, 'public.machine_session_credentials', 'INSERT'),
                       has_table_privilege(current_user, 'public.machine_session_credentials', 'UPDATE'),
                       has_table_privilege(current_user, 'public.machine_session_credentials', 'DELETE')
            """)).one()
            assert tuple(privileges) == (False, True, False, False)
            worker_function_privileges = connection.execute(text("""
                SELECT
                    has_function_privilege(current_user,
                      'agency_os_private.load_mcp_provider_credential(text)', 'EXECUTE'),
                    has_function_privilege(current_user,
                      'agency_os_private.attach_mcp_provider_credential(text,text,text)', 'EXECUTE'),
                    has_function_privilege(current_user,
                      'agency_os_private.revoke_mcp_session_credential(text,text)', 'EXECUTE'),
                    has_function_privilege(current_user,
                      'agency_os_private.mark_mcp_provider_credential_archived(text,text)', 'EXECUTE')
            """)).one()
            assert tuple(worker_function_privileges) == (True, True, True, True)

            # Caller-forged tenant GUCs cannot satisfy the execution-bound INSERT policy.
            connection.execute(
                text("SELECT set_config('agency_os.machine_org_id', :org, true)"),
                {"org": expected[0]},
            )
            connection.execute(
                text("SELECT set_config('agency_os.machine_workspace_id', :workspace, true)"),
                {"workspace": expected[1]},
            )
            with pytest.raises(DBAPIError):
                connection.execute(text("""
                    INSERT INTO public.machine_session_credentials (
                        id, org_id, workspace_id, machine_identity_id, session_id,
                        token_hash, token_prefix, credential_version, expires_at,
                        request_count_window, provider_credential_status
                    ) VALUES (
                        :id, :org, :workspace, :identity, :session,
                        :hash, 'aos_ms_forged.', 1, now() + interval '5 minutes',
                        0, 'not_created'
                    )
                """), {
                    "id": str(uuid.uuid4()), "org": expected[0], "workspace": expected[1],
                    "identity": expected[2], "session": expected[3],
                    "hash": hashlib.sha256(f"forged-{suffix}".encode()).hexdigest(),
                })
            connection.rollback()
            # The worker may call the bounded lifecycle functions, but forged
            # tenant GUCs cannot make them act without a live execution capability.
            assert connection.execute(text("""
                SELECT * FROM agency_os_private.load_mcp_provider_credential(:execution_id)
            """), {"execution_id": "f1b2c3d4-e5f6-4789-9012-1234567890ab"}).all() == []
            assert connection.execute(text("""
                SELECT agency_os_private.attach_mcp_provider_credential(
                    :credential_id, 'vlt_test', 'cred_test'
                )
            """), {"credential_id": credential_id}).scalar_one() is False
            assert connection.execute(text("""
                SELECT agency_os_private.revoke_mcp_session_credential(
                    :credential_id, 'TEST_FORGED_CONTEXT'
                )
            """), {"credential_id": credential_id}).scalar_one() is False
            assert connection.execute(text("""
                SELECT agency_os_private.mark_mcp_provider_credential_archived(
                    :credential_id, 'cred_test'
                )
            """), {"credential_id": credential_id}).scalar_one() is False
            connection.rollback()

        with Admin() as db:
            db.query(AgentSession).filter_by(id=expected[3]).update({"status": "cancelled"})
            db.commit()
        with app_engine.connect() as connection:
            active_after_cancel = connection.execute(text("""
                SELECT agency_os_private.is_mcp_session_credential_active(
                    :id, :digest, :org, :workspace, :identity, :session
                )
            """), {
                "id": credential_id, "digest": token_hash, "org": expected[0],
                "workspace": expected[1], "identity": expected[2], "session": expected[3],
            }).scalar_one()
            assert active_after_cancel is False
            connection.commit()
    finally:
        with Admin() as db:
            db.query(MachineSessionCredential).filter_by(id=credential_id).delete(synchronize_session=False)
            db.query(Execution).filter(Execution.id == f"mcp-exec-{suffix}").delete(synchronize_session=False)
            db.query(AgentSession).filter(AgentSession.id == f"mcp-session-{suffix}").delete(synchronize_session=False)
            db.query(MachineIdentity).filter(MachineIdentity.id == f"mcp-mi-{suffix}").delete(synchronize_session=False)
            db.query(Task).filter(Task.id == f"mcp-task-{suffix}").delete(synchronize_session=False)
            db.query(Agent).filter(Agent.id == f"mcp-agent-{suffix}").delete(synchronize_session=False)
            db.query(Workspace).filter(Workspace.id == f"mcp-ws-{suffix}").delete(synchronize_session=False)
            db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
            db.query(Organization).filter(Organization.id == org.id).delete(synchronize_session=False)
            db.commit()
        worker_engine.dispose()
        app_engine.dispose()
        admin_engine.dispose()
