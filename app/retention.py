"""Bounded workspace-scoped retention scrubbing for sensitive session/tool payloads.

Identity, idempotency and audit records remain durable. Only descriptive and
request/result payload fields are scrubbed after their configured retention.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.audit import record_event
from app.security_models import AgentSession, ToolInvocation


def purge_due_retention_data(
    db: Session,
    *,
    limit: int = 100,
    agent_session_days: int = 90,
    tool_invocation_payload_days: int = 180,
    now: datetime | None = None,
) -> dict[str, int]:
    """Scrub old terminal-session descriptions and completed invocation payloads.

    The caller must provide a workspace-scoped worker or authorized human
    session. This function never deletes rows, keys, hashes, statuses or audit.
    Each table is independently bounded by limit.
    """
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    if not 1 <= agent_session_days <= 3650:
        raise ValueError("agent_session_days must be between 1 and 3650")
    if not 1 <= tool_invocation_payload_days <= 3650:
        raise ValueError("tool_invocation_payload_days must be between 1 and 3650")

    now = now or datetime.now(timezone.utc)
    session_cutoff = now - timedelta(days=agent_session_days)
    invocation_cutoff = now - timedelta(days=tool_invocation_payload_days)

    sessions = (
        db.query(AgentSession)
        .filter(
            AgentSession.status.in_(("cancelled", "expired", "closed")),
            AgentSession.ended_at.is_not(None),
            AgentSession.ended_at <= session_cutoff,
            AgentSession.metadata_purged_at.is_(None),
        )
        .order_by(AgentSession.ended_at.asc(), AgentSession.id.asc())
        .with_for_update(skip_locked=True)
        .limit(limit)
        .all()
    )
    for session in sessions:
        session.purpose = "[retained metadata]"
        session.metadata_purged_at = now
        record_event(
            db, session.org_id, None, "agent_session.metadata_purged",
            "agent_session", session.id, session.workspace_id,
            {
                "machine_identity_id": session.machine_identity_id,
                "reason_code": "AGENT_SESSION_RETENTION_ELAPSED",
            },
        )

    invocations = (
        db.query(ToolInvocation)
        .filter(
            ToolInvocation.finished_at.is_not(None),
            ToolInvocation.finished_at <= invocation_cutoff,
            ToolInvocation.payload_purged_at.is_(None),
        )
        .order_by(ToolInvocation.finished_at.asc(), ToolInvocation.id.asc())
        .with_for_update(skip_locked=True)
        .limit(limit)
        .all()
    )
    for invocation in invocations:
        invocation.request_payload = {}
        invocation.result = None
        invocation.payload_purged_at = now
        record_event(
            db, invocation.org_id, None, "tool.invocation.payload_purged",
            "tool_invocation", invocation.id, invocation.workspace_id,
            {
                "machine_identity_id": invocation.machine_identity_id,
                "session_id": invocation.session_id,
                "tool_key": invocation.tool_key,
                "reason_code": "TOOL_PAYLOAD_RETENTION_ELAPSED",
            },
        )

    if sessions or invocations:
        db.flush()
    return {
        "agent_sessions_scrubbed": len(sessions),
        "tool_payloads_purged": len(invocations),
    }
