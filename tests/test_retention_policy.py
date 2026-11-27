from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import AuditEvent, Organization, Workspace, User
from app.security_models import AgentSession, MachineIdentity, ToolInvocation
from app.retention import purge_due_retention_data


def _database():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import app.models  # noqa: F401
    import app.security_models  # noqa: F401
    Base.metadata.create_all(engine)
    return engine


def test_retention_scrubs_old_session_metadata_and_tool_payloads_but_keeps_tombstones():
    engine = _database()
    now = datetime.now(timezone.utc)
    try:
        with Session(engine, expire_on_commit=False) as db:
            org = Organization(name="Retention test")
            db.add(org)
            db.flush()
            workspace = Workspace(org_id=org.id, name="Synthetic workspace")
            db.add(workspace)
            db.flush()
            identity = MachineIdentity(
                org_id=org.id, workspace_id=workspace.id, name="Synthetic agent",
                subject_type="agent", subject_id="agent-1", token_hash="a" * 64,
                token_prefix="aos_mi_test", scopes=[], allowed_data_classes=["synthetic"],
                expires_at=now + timedelta(days=365), created_by_user_id=None,
            )
            # Machine identities require a creator FK; use a minimal user fixture.
            user = User(email="retention@example.test")
            db.add(user)
            db.flush()
            identity.created_by_user_id = user.id
            db.add(identity)
            db.flush()
            old_session = AgentSession(
                org_id=org.id, workspace_id=workspace.id, machine_identity_id=identity.id,
                purpose="Sensitive client-specific session description", data_class="synthetic",
                status="closed", created_at=now - timedelta(days=100),
                last_seen_at=now - timedelta(days=100), expires_at=now - timedelta(days=99),
                ended_at=now - timedelta(days=91),
            )
            recent_session = AgentSession(
                org_id=org.id, workspace_id=workspace.id, machine_identity_id=identity.id,
                purpose="Keep this recent description", data_class="synthetic",
                status="closed", created_at=now - timedelta(days=20),
                last_seen_at=now - timedelta(days=20), expires_at=now - timedelta(days=19),
                ended_at=now - timedelta(days=10),
            )
            db.add_all([old_session, recent_session])
            db.flush()
            invocation = ToolInvocation(
                org_id=org.id, workspace_id=workspace.id, machine_identity_id=identity.id,
                session_id=old_session.id, tool_key="revenue.lookup", tool_version="1",
                idempotency_key="retention-idempotency-key",
                request_hash="b" * 64, request_payload={"email": "client@example.test"},
                result={"lead_id": "lead-1"}, status="succeeded",
                created_at=now - timedelta(days=200), finished_at=now - timedelta(days=181),
            )
            recent_invocation = ToolInvocation(
                org_id=org.id, workspace_id=workspace.id, machine_identity_id=identity.id,
                session_id=recent_session.id, tool_key="revenue.lookup", tool_version="1",
                idempotency_key="recent-idempotency-key",
                request_hash="c" * 64, request_payload={"query": "recent"},
                result={"lead_id": "lead-2"}, status="succeeded",
                created_at=now - timedelta(days=20), finished_at=now - timedelta(days=10),
            )
            db.add_all([invocation, recent_invocation])
            db.flush()
            old_session_id, recent_session_id = old_session.id, recent_session.id
            invocation_id, recent_invocation_id = invocation.id, recent_invocation.id

            result = purge_due_retention_data(
                db,
                limit=10,
                agent_session_days=90,
                tool_invocation_payload_days=180,
                now=now,
            )
            assert result == {"agent_sessions_scrubbed": 1, "tool_payloads_purged": 1}
            db.commit()

            old_session = db.get(AgentSession, old_session_id)
            recent_session = db.get(AgentSession, recent_session_id)
            assert old_session.purpose == "[retained metadata]"
            assert old_session.metadata_purged_at is not None
            assert recent_session.purpose == "Keep this recent description"
            assert recent_session.metadata_purged_at is None

            invocation = db.get(ToolInvocation, invocation_id)
            recent_invocation = db.get(ToolInvocation, recent_invocation_id)
            assert invocation.request_payload == {}
            assert invocation.result is None
            assert invocation.payload_purged_at is not None
            assert invocation.idempotency_key == "retention-idempotency-key"
            assert invocation.request_hash == "b" * 64
            assert invocation.status == "succeeded"
            assert recent_invocation.request_payload == {"query": "recent"}
            assert recent_invocation.result == {"lead_id": "lead-2"}
            assert recent_invocation.payload_purged_at is None

            events = db.query(AuditEvent).filter(
                AuditEvent.event_type.in_(( 
                    "agent_session.metadata_purged",
                    "tool.invocation.payload_purged",
                ))
            ).all()
            assert {event.event_type for event in events} == {
                "agent_session.metadata_purged",
                "tool.invocation.payload_purged",
            }
            assert all(
                event.payload["reason_code"] in {
                    "AGENT_SESSION_RETENTION_ELAPSED",
                    "TOOL_PAYLOAD_RETENTION_ELAPSED",
                }
                for event in events
            )
    finally:
        engine.dispose()
