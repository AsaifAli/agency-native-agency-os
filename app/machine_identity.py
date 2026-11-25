"""Machine credential issuance, authentication and session authorization primitives."""
from __future__ import annotations
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from app.security_models import AgentSession, MachineIdentity

TOKEN_PREFIX = "aos_mi_"
ALLOWED_SUBJECT_TYPES = {"agent", "worker", "service"}
ALLOWED_DATA_CLASSES = {"synthetic", "public", "commercial", "confidential", "regulated"}

@dataclass(frozen=True)
class MachinePrincipal:
    identity: MachineIdentity

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

def _token_digest(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()

def issue_machine_credential() -> tuple[str, str, str]:
    """Return raw secret, one-way digest and non-secret display prefix."""
    secret = secrets.token_urlsafe(32)
    return secret, _token_digest(secret), TOKEN_PREFIX + secret[:8]

def authenticate_machine_token(authorization: str | None, db: Session) -> MachinePrincipal:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Machine bearer token required")
    token = authorization.removeprefix("Bearer ").strip()
    if not token.startswith(TOKEN_PREFIX) or "." not in token:
        raise HTTPException(401, "Invalid machine credential")
    identity_id, secret = token[len(TOKEN_PREFIX):].split(".", 1)
    if not identity_id or not secret or len(secret) > 256:
        raise HTTPException(401, "Invalid machine credential")
    identity = db.query(MachineIdentity).filter(MachineIdentity.id == identity_id).first()
    if identity is None or identity.revoked_at is not None:
        raise HTTPException(401, "Invalid or revoked machine credential")
    if identity.expires_at <= _utcnow():
        raise HTTPException(401, "Machine credential expired")
    if not hmac.compare_digest(identity.token_hash, _token_digest(secret)):
        raise HTTPException(401, "Invalid machine credential")
    identity.last_used_at = _utcnow()
    return MachinePrincipal(identity=identity)

def get_machine_principal(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> MachinePrincipal:
    return authenticate_machine_token(authorization, db)

def create_agent_session(db: Session, principal: MachinePrincipal, *, purpose: str, data_class: str, ttl_seconds: int) -> AgentSession:
    identity = principal.identity
    now = _utcnow()
    if identity.revoked_at is not None or identity.expires_at <= now:
        raise HTTPException(401, "Machine credential is no longer active")
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
    expires_at = min(now + timedelta(seconds=ttl_seconds), identity.expires_at)
    if expires_at <= now:
        raise HTTPException(401, "Machine credential is expired")
    session = AgentSession(org_id=identity.org_id, workspace_id=identity.workspace_id, machine_identity_id=identity.id, purpose=purpose.strip(), data_class=data_class, status="active", created_at=now, last_seen_at=now, expires_at=expires_at)
    db.add(session)
    db.flush()
    return session

def authorize_tool_session(db: Session, principal: MachinePrincipal, *, session_id: str, tool_key: str, data_class: str) -> AgentSession:
    """Fail-closed authorization primitive for the forthcoming OS Tool Gateway.

    This does not execute tools. A gateway adapter must call it before dispatch
    and persist its invocation/result/audit lifecycle.
    """
    identity = principal.identity
    now = _utcnow()
    if identity.revoked_at is not None or identity.expires_at <= now:
        raise HTTPException(401, "Machine credential is no longer active")
    session = db.query(AgentSession).filter_by(id=session_id, org_id=identity.org_id, workspace_id=identity.workspace_id, machine_identity_id=identity.id).with_for_update().first()
    if session is None:
        raise HTTPException(404, "Session not found")
    if session.status != "active" or session.expires_at <= now:
        if session.status == "active" and session.expires_at <= now:
            session.status = "expired"
            session.ended_at = now
        raise HTTPException(409, "Session is not active")
    if data_class not in ALLOWED_DATA_CLASSES:
        raise HTTPException(422, "Unsupported data class")
    if data_class != session.data_class or data_class not in identity.allowed_data_classes:
        raise HTTPException(403, "Tool data class is outside the session grant")
    if "tools:invoke" not in identity.scopes or f"tool:{tool_key}" not in identity.scopes:
        raise HTTPException(403, "Tool is not granted to this machine identity")
    session.last_seen_at = now
    identity.last_used_at = now
    return session
