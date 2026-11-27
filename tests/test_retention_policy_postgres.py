"""PostgreSQL test for retention under a real workspace maintenance capability."""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.models import AuditEvent, Organization, User, Workspace
from app.security_models import AgentSession, MachineIdentity, ToolInvocation
from app.retention import purge_due_retention_data
from app.db import scoped_worker_workspace_session_factory
from app.worker_service import claim_worker_maintenance_scope

ADMIN_URL = os.getenv("AGENCY_OS_TEST_DATABASE_URL")
WORKER_URL = os.getenv("AGENCY_OS_TEST_RLS_WORKER_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not (ADMIN_URL and WORKER_URL),
    reason="Set admin and worker PostgreSQL URLs for retention capability tests",
)


def test_retention_scrubbing_runs_only_with_exact_workspace_capability():
    for url in (ADMIN_URL, WORKER_URL):
        parsed = make_url(url)
        assert parsed.get_backend_name() == "postgresql"
        assert parsed.database == "agency_os_worker_test", (
            "Safety check: retention tests may only use agency_os_worker_test"
        )

    admin_engine = create_engine(ADMIN_URL, pool_pre_ping=True)
    worker_engine = create_engine(WORKER_URL, pool_pre_ping=True)
    Admin = sessionmaker(bind=admin_engine, expire_on_commit=False)
    Worker = sessionmaker(bind=worker_engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc)
    user = User(email=f"retention-pg-{suffix}@example.test")
    org = Organization(name=f"Retention PG {suffix}")
    org_id = workspace_id = session_id = invocation_id = identity_id = None
    capability = None
    workspace_factory = None
    try:
        with Admin() as db:
            db.add_all([user, org])
            db.flush()
            workspace = Workspace(
                id=f"00000000-0000-4000-8000-{suffix}",
                org_id=org.id,
                name="Retention capability test",
                created_by=user.id,
            )
            db.add(workspace)
            db.flush()
            identity = MachineIdentity(
                org_id=org.id,
                workspace_id=workspace.id,
                name="Retention synthetic agent",
                subject_type="agent",
                subject_id=f"agent-{suffix}",
                token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                token_prefix="aos_mi_retention",
                scopes=[],
                allowed_data_classes=["synthetic"],
                expires_at=now + timedelta(days=365),
                created_by_user_id=user.id,
            )
            db.add(identity)
            db.flush()
            session = AgentSession(
                org_id=org.id,
                workspace_id=workspace.id,
                machine_identity_id=identity.id,
                purpose="Sensitive synthetic test session description",
                data_class="synthetic",
                status="closed",
                created_at=now - timedelta(days=100),
                last_seen_at=now - timedelta(days=100),
                expires_at=now - timedelta(days=99),
                ended_at=now - timedelta(days=91),
            )
            db.add(session)
            db.flush()
            invocation = ToolInvocation(
                org_id=org.id,
                workspace_id=workspace.id,
                machine_identity_id=identity.id,
                session_id=session.id,
                tool_key="revenue.lookup",
                tool_version="1",
                idempotency_key=f"retention-pg-{suffix}",
                request_hash="d" * 64,
                request_payload={"synthetic": "payload"},
                result={"draft_id": f"draft-{suffix}"},
                status="succeeded",
                created_at=now - timedelta(days=200),
                finished_at=now - timedelta(days=181),
            )
            db.add(invocation)
            db.commit()
            org_id, workspace_id = org.id, workspace.id
            session_id, invocation_id, identity_id = session.id, invocation.id, identity.id

        with Worker() as claim_db:
            capability = claim_worker_maintenance_scope(
                claim_db, worker_id=f"retention-{suffix}", lease_seconds=120,
            )
            assert capability is not None
            assert capability.workspace_id == workspace_id, (
                "The isolated retention test DB must have no other unclaimed workspaces"
            )
            claim_db.commit()

        workspace_factory = scoped_worker_workspace_session_factory(capability, Worker)
        with workspace_factory() as db:
            result = purge_due_retention_data(
                db,
                limit=10,
                agent_session_days=90,
                tool_invocation_payload_days=180,
                now=now,
            )
            assert result == {"agent_sessions_scrubbed": 1, "tool_payloads_purged": 1}
            db.commit()

        with Admin() as db:
            session = db.get(AgentSession, session_id)
            invocation = db.get(ToolInvocation, invocation_id)
            assert session.purpose == "[retained metadata]"
            assert session.metadata_purged_at is not None
            assert invocation.request_payload == {}
            assert invocation.result is None
            assert invocation.payload_purged_at is not None
            assert invocation.idempotency_key == f"retention-pg-{suffix}"
            assert invocation.request_hash == "d" * 64
            events = db.query(AuditEvent).filter(
                AuditEvent.org_id == org_id,
                AuditEvent.event_type.in_((
                    "agent_session.metadata_purged",
                    "tool.invocation.payload_purged",
                )),
            ).all()
            assert len(events) == 2

        with workspace_factory() as db:
            released = db.execute(text(
                "SELECT agency_os_private.release_worker_maintenance_scope()"
            )).scalar_one()
            assert released is True
            db.commit()
        capability = None
    finally:
        if capability is not None and workspace_factory is not None:
            try:
                with workspace_factory() as db:
                    db.execute(text(
                        "SELECT agency_os_private.release_worker_maintenance_scope()"
                    ))
                    db.commit()
            except Exception:
                pass
        with Admin() as db:
            if org_id is not None:
                db.execute(text("DELETE FROM public.audit_events WHERE org_id = :org"), {"org": org_id})
                db.execute(text("DELETE FROM public.tool_invocations WHERE org_id = :org"), {"org": org_id})
                db.execute(text("DELETE FROM public.agent_sessions WHERE org_id = :org"), {"org": org_id})
                db.execute(text("DELETE FROM public.machine_identities WHERE org_id = :org"), {"org": org_id})
                db.execute(text("DELETE FROM public.workspaces WHERE org_id = :org"), {"org": org_id})
                db.execute(text("DELETE FROM public.organizations WHERE id = :org"), {"org": org_id})
                db.execute(text("DELETE FROM public.users WHERE id = :user"), {"user": user.id})
                db.commit()
        worker_engine.dispose()
        admin_engine.dispose()
