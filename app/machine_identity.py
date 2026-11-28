"""Machine credential issuance, authentication and session authorization primitives."""
from __future__ import annotations
import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db, set_rls_context
from app.audit import record_event
from app.data_protection import DataProtectionBlocked, sanitize_text
from app.security_models import AgentSession, MachineIdentity

TOKEN_PREFIX = "aos_mi_"
ALLOWED_SUBJECT_TYPES = {"agent", "worker", "service"}
ALLOWED_DATA_CLASSES = {"synthetic", "public"}

@dataclass(frozen=True)
class MachinePrincipal:
    identity: MachineIdentity

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

def _as_utc(value: datetime) -> datetime:
    # SQLite drops timezone metadata for DateTime(timezone=True); normalize reads.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

def _token_digest(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()

def issue_machine_credential() -> tuple[str, str, str]:
    """Return raw secret, one-way digest and non-secret display prefix."""
    secret = secrets.token_urlsafe(32)
    return secret, _token_digest(secret), TOKEN_PREFIX + secret[:8]

def _require_enabled_agent_subject(db: Session, identity: MachineIdentity) -> None:
    """Reject credentials whose bound Agent definition has been disabled."""
    if identity.subject_type != "agent":
        return
    from app.models import Agent

    agent = db.query(Agent).filter_by(
        id=identity.subject_id,
        org_id=identity.org_id,
        workspace_id=identity.workspace_id,
    ).with_for_update().first()
    if agent is None or not agent.enabled:
        raise HTTPException(401, "Agent machine identity is no longer active")


def _require_active_agent_workforce_member(db: Session, identity: MachineIdentity) -> None:
    """Require one active workforce owner before an agent can create a session."""
    if identity.subject_type != "agent":
        return
    from app.workforce_models import WorkforceMember

    members = db.query(WorkforceMember).filter_by(
        org_id=identity.org_id,
        workspace_id=identity.workspace_id,
        agent_id=identity.subject_id,
    ).with_for_update().all()
    if (
        len(members) != 1
        or members[0].status != "active"
        or members[0].is_founder_reserved
    ):
        raise HTTPException(403, "Agent has no single active workforce assignment")


def authenticate_machine_token(authorization: str | None, db: Session) -> MachinePrincipal:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Machine bearer token required")
    token = authorization.removeprefix("Bearer ").strip()
    if len(token) > 512 or not token.startswith(TOKEN_PREFIX) or "." not in token:
        raise HTTPException(401, "Invalid machine credential")
    identity_id, secret = token[len(TOKEN_PREFIX):].split(".", 1)
    if not identity_id or len(identity_id) > 36 or not secret or len(secret) > 256:
        raise HTTPException(401, "Invalid machine credential")
    set_rls_context(db, machine_identity_lookup_id=identity_id)
    identity = db.query(MachineIdentity).filter(MachineIdentity.id == identity_id).first()
    if identity is None or identity.revoked_at is not None:
        raise HTTPException(401, "Invalid or revoked machine credential")
    if _as_utc(identity.expires_at) <= _utcnow():
        raise HTTPException(401, "Machine credential expired")
    if not hmac.compare_digest(identity.token_hash, _token_digest(secret)):
        raise HTTPException(401, "Invalid machine credential")
    set_rls_context(db, machine_org_id=identity.org_id, machine_workspace_id=identity.workspace_id, machine_identity_lookup_id=identity.id)
    _require_enabled_agent_subject(db, identity)
    identity.last_used_at = _utcnow()
    return MachinePrincipal(identity=identity)

def get_machine_principal(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> MachinePrincipal:
    return authenticate_machine_token(authorization, db)

def _lock_active_identity(db: Session, principal: MachinePrincipal) -> MachineIdentity:
    identity = db.query(MachineIdentity).filter_by(
        id=principal.identity.id,
        org_id=principal.identity.org_id,
        workspace_id=principal.identity.workspace_id,
    ).with_for_update().first()
    if identity is None or identity.revoked_at is not None or _as_utc(identity.expires_at) <= _utcnow():
        raise HTTPException(401, "Machine credential is no longer active")
    _require_enabled_agent_subject(db, identity)
    return identity

def create_agent_session(db: Session, principal: MachinePrincipal, *, purpose: str, data_class: str, ttl_seconds: int) -> AgentSession:
    # Serialize with founder revocation so a session cannot be created concurrently
    # after the identity has been revoked.
    identity = _lock_active_identity(db, principal)
    _require_active_agent_workforce_member(db, identity)
    now = _utcnow()
    identity_expiry = _as_utc(identity.expires_at)
    if "sessions:create" not in identity.scopes:
        raise HTTPException(403, "Machine identity cannot create sessions")
    if data_class not in ALLOWED_DATA_CLASSES:
        raise HTTPException(422, "Unsupported data class")
    if data_class not in identity.allowed_data_classes:
        raise HTTPException(403, "Data class is outside the machine identity grant")
    if not 60 <= ttl_seconds <= 86400:
        raise HTTPException(422, "Session TTL must be between 60 and 86400 seconds")
    if not purpose or len(purpose.strip()) > 240:
        raise HTTPException(422, "A session purpose of at most 240 characters is required")
    try:
        safe_purpose, _ = sanitize_text(purpose.strip())
    except DataProtectionBlocked as exc:
        raise HTTPException(422, "Session purpose blocked by data-protection policy") from exc
    if not safe_purpose:
        raise HTTPException(422, "Session purpose is empty after data protection")
    expires_at = min(now + timedelta(seconds=ttl_seconds), identity_expiry)
    if expires_at <= now:
        raise HTTPException(401, "Machine credential is expired")
    session = AgentSession(
        org_id=identity.org_id, workspace_id=identity.workspace_id,
        machine_identity_id=identity.id, purpose=safe_purpose,
        data_class=data_class, status="active", created_at=now,
        last_seen_at=now, expires_at=expires_at,
    )
    db.add(session)
    db.flush()
    return session

def authorize_tool_session(db: Session, principal: MachinePrincipal, *, session_id: str, tool_key: str, data_class: str) -> AgentSession:
    """Fail-closed authorization primitive for the forthcoming OS Tool Gateway.

    This does not execute tools. A gateway adapter must call it before dispatch
    and persist its invocation/result/audit lifecycle.
    """
    identity = _lock_active_identity(db, principal)
    now = _utcnow()
    session = db.query(AgentSession).filter_by(
        id=session_id, org_id=identity.org_id,
        workspace_id=identity.workspace_id, machine_identity_id=identity.id,
    ).with_for_update().first()
    if session is None:
        raise HTTPException(404, "Session not found")
    if session.status != "active" or _as_utc(session.expires_at) <= now:
        raise HTTPException(409, "Session is not active")
    if data_class not in ALLOWED_DATA_CLASSES:
        raise HTTPException(422, "Unsupported data class")
    if data_class != session.data_class or data_class not in identity.allowed_data_classes:
        raise HTTPException(403, "Tool data class is outside the session grant")
    if not isinstance(tool_key, str) or not re.fullmatch(r"[a-z0-9_.-]{1,100}", tool_key):
        raise HTTPException(422, "Invalid tool key")
    if "tools:invoke" not in identity.scopes or f"tool:{tool_key}" not in identity.scopes:
        raise HTTPException(403, "Tool is not granted to this machine identity")
    session.last_seen_at = now
    identity.last_used_at = now
    return session



def expire_due_agent_sessions(db: Session, *, limit: int = 100) -> int:
    """Expire a bounded batch of sessions and audit each transition.

    Caller owns the transaction. Row locks make concurrent worker sweeps safe.
    """
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    now = _utcnow()
    rows = (
        db.query(AgentSession)
        .filter(AgentSession.status == "active", AgentSession.expires_at <= now)
        .order_by(AgentSession.expires_at.asc(), AgentSession.id.asc())
        .with_for_update(skip_locked=True)
        .limit(limit)
        .all()
    )
    for session in rows:
        session.status = "expired"
        session.ended_at = now
        record_event(
            db, session.org_id, None, "agent_session.expired",
            "agent_session", session.id, session.workspace_id,
            {"machine_identity_id": session.machine_identity_id,
             "reason_code": "SESSION_TTL_EXPIRED"},
        )
    if rows:
        db.flush()
    return len(rows)
