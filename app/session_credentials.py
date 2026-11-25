"""Short-lived bearer credentials bound to one Agency OS agent session."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.audit import record_event
from app.machine_identity import MachinePrincipal
from app.security_models import AgentSession, MachineIdentity, MachineSessionCredential


_TOKEN_PREFIX = "aos_ms_"
_TOKEN_SECRET_RE = re.compile(r"^[A-Za-z0-9_-]{40,64}$")
_CREDENTIAL_ID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")
_ALLOWED_MCP_DATA_CLASSES = {"public", "synthetic"}


@dataclass(frozen=True)
class IssuedSessionCredential:
    credential_id: str
    token: str
    expires_at: datetime
    credential_version: int


@dataclass(frozen=True)
class SessionCredentialContext:
    org_id: str
    workspace_id: str
    machine_identity_id: str
    session_id: str
    credential_id: str


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _unauthorized() -> HTTPException:
    return HTTPException(status_code=401, detail="Invalid or expired session credential.")


def _lock_identity(db: Session, org_id: str, workspace_id: str, identity_id: str, now: datetime) -> MachineIdentity:
    identity = (
        db.query(MachineIdentity)
        .filter_by(id=identity_id, org_id=org_id, workspace_id=workspace_id)
        .with_for_update()
        .first()
    )
    if (
        identity is None
        or identity.revoked_at is not None
        or _as_utc(identity.expires_at) <= now
    ):
        raise _unauthorized()
    return identity


def _lock_session(
    db: Session,
    *,
    org_id: str,
    workspace_id: str,
    identity_id: str,
    session_id: str,
    now: datetime,
) -> AgentSession:
    session = (
        db.query(AgentSession)
        .filter_by(
            id=session_id,
            org_id=org_id,
            workspace_id=workspace_id,
            machine_identity_id=identity_id,
        )
        .with_for_update()
        .first()
    )
    if (
        session is None
        or session.status != "active"
        or _as_utc(session.expires_at) <= now
        or session.data_class not in _ALLOWED_MCP_DATA_CLASSES
    ):
        raise _unauthorized()
    return session


def revoke_session_credentials_for_session(
    db: Session,
    session: AgentSession,
    *,
    reason_code: str,
    now: datetime | None = None,
) -> int:
    """Revoke all active credentials for a session; caller holds identity/session locks."""
    now = now or datetime.now(timezone.utc)
    credentials = (
        db.query(MachineSessionCredential)
        .filter_by(
            org_id=session.org_id,
            workspace_id=session.workspace_id,
            session_id=session.id,
        )
        .filter(MachineSessionCredential.revoked_at.is_(None))
        .with_for_update()
        .all()
    )
    for credential in credentials:
        credential.revoked_at = now
        credential.revocation_reason = reason_code[:80]
        if credential.provider_credential_id and credential.provider_credential_status == "active":
            credential.provider_credential_status = "delete_pending"
        record_event(
            db,
            session.org_id,
            None,
            "machine_session_credential.revoked",
            "machine_session_credential",
            credential.id,
            session.workspace_id,
            {
                "session_id": session.id,
                "machine_identity_id": session.machine_identity_id,
                "reason_code": reason_code[:80],
            },
        )
    return len(credentials)


def issue_session_credential(
    db: Session,
    principal: MachinePrincipal,
    *,
    session_id: str,
    ttl_seconds: int = 900,
    now: datetime | None = None,
) -> IssuedSessionCredential:
    """Issue a one-session bearer token. The raw token is returned once and never stored."""
    now = now or datetime.now(timezone.utc)
    ttl_seconds = max(60, min(int(ttl_seconds), 3600))
    identity = _lock_identity(
        db,
        principal.identity.org_id,
        principal.identity.workspace_id,
        principal.identity.id,
        now,
    )
    session = _lock_session(
        db,
        org_id=identity.org_id,
        workspace_id=identity.workspace_id,
        identity_id=identity.id,
        session_id=session_id,
        now=now,
    )
    if session.data_class not in identity.allowed_data_classes:
        raise HTTPException(status_code=403, detail="Session credential is not permitted by OS policy.")

    # Rotate under the session row lock. Old provider-held tokens stop working
    # before the new credential is committed.
    revoke_session_credentials_for_session(
        db, session, reason_code="CREDENTIAL_ROTATED", now=now
    )
    previous_version = (
        db.query(MachineSessionCredential.credential_version)
        .filter_by(
            org_id=identity.org_id,
            workspace_id=identity.workspace_id,
            session_id=session.id,
        )
        .order_by(MachineSessionCredential.credential_version.desc())
        .first()
    )
    version = (previous_version[0] if previous_version else 0) + 1
    credential_id = str(uuid.uuid4())
    secret = secrets.token_urlsafe(32)
    token = f"{_TOKEN_PREFIX}{credential_id}.{secret}"
    expires_at = min(
        now + timedelta(seconds=ttl_seconds),
        _as_utc(session.expires_at),
        _as_utc(identity.expires_at),
    )
    if expires_at <= now:
        raise HTTPException(status_code=409, detail="Session or machine identity is expiring.")
    credential = MachineSessionCredential(
        id=credential_id,
        org_id=identity.org_id,
        workspace_id=identity.workspace_id,
        machine_identity_id=identity.id,
        session_id=session.id,
        token_hash=hashlib.sha256(secret.encode("utf-8")).hexdigest(),
        token_prefix=f"{_TOKEN_PREFIX}{credential_id}.",
        credential_version=version,
        expires_at=expires_at,
        request_window_started_at=now,
        request_count_window=0,
    )
    db.add(credential)
    record_event(
        db,
        identity.org_id,
        None,
        "machine_session_credential.issued",
        "machine_session_credential",
        credential.id,
        identity.workspace_id,
        {
            "machine_identity_id": identity.id,
            "session_id": session.id,
            "credential_version": version,
            "expires_at": expires_at.isoformat(),
        },
    )
    db.commit()
    return IssuedSessionCredential(
        credential_id=credential.id,
        token=token,
        expires_at=expires_at,
        credential_version=version,
    )


def authenticate_session_credential(
    db: Session,
    authorization: str | None,
    *,
    requests_per_minute: int = 120,
    now: datetime | None = None,
) -> SessionCredentialContext:
    """Authenticate a session token and durably update use/rate-limit counters."""
    now = now or datetime.now(timezone.utc)
    if not isinstance(authorization, str):
        raise _unauthorized()
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer":
        raise _unauthorized()
    token = token.strip()
    if not token.startswith(_TOKEN_PREFIX):
        raise _unauthorized()
    token_id_and_secret = token[len(_TOKEN_PREFIX):]
    credential_id, separator, secret = token_id_and_secret.partition(".")
    if (
        not separator
        or not _CREDENTIAL_ID_RE.fullmatch(credential_id)
        or not _TOKEN_SECRET_RE.fullmatch(secret)
    ):
        raise _unauthorized()

    hint = db.query(MachineSessionCredential).filter_by(id=credential_id).first()
    if hint is None:
        raise _unauthorized()
    presented_hash = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(hint.token_hash, presented_hash):
        raise _unauthorized()

    # Lock order is identity -> session -> credential, matching revocation.
    identity = _lock_identity(
        db, hint.org_id, hint.workspace_id, hint.machine_identity_id, now
    )
    session = _lock_session(
        db,
        org_id=hint.org_id,
        workspace_id=hint.workspace_id,
        identity_id=identity.id,
        session_id=hint.session_id,
        now=now,
    )
    credential = (
        db.query(MachineSessionCredential)
        .filter_by(
            id=credential_id,
            org_id=hint.org_id,
            workspace_id=hint.workspace_id,
            machine_identity_id=identity.id,
            session_id=session.id,
        )
        .with_for_update()
        .first()
    )
    if (
        credential is None
        or credential.revoked_at is not None
        or _as_utc(credential.expires_at) <= now
        or not hmac.compare_digest(
            credential.token_hash,
            presented_hash,
        )
    ):
        raise _unauthorized()

    window_started = credential.request_window_started_at
    if window_started is None or (now - _as_utc(window_started)).total_seconds() >= 60:
        credential.request_window_started_at = now
        credential.request_count_window = 0
    if credential.request_count_window >= max(1, requests_per_minute):
        record_event(
            db,
            identity.org_id,
            None,
            "machine_session_credential.rate_limited",
            "machine_session_credential",
            credential.id,
            identity.workspace_id,
            {
                "session_id": session.id,
                "reason_code": "REQUEST_RATE_LIMITED",
                "limit_per_minute": max(1, requests_per_minute),
            },
        )
        db.commit()
        raise HTTPException(status_code=429, detail="Session request limit exceeded.")

    credential.request_count_window += 1
    credential.last_used_at = now
    identity.last_used_at = now
    session.last_seen_at = now
    db.commit()
    return SessionCredentialContext(
        org_id=identity.org_id,
        workspace_id=identity.workspace_id,
        machine_identity_id=identity.id,
        session_id=session.id,
        credential_id=credential.id,
    )


def load_active_session_context(
    db: Session,
    context: SessionCredentialContext,
    *,
    now: datetime | None = None,
) -> tuple[MachinePrincipal, AgentSession]:
    """Revalidate the credential, identity and session at tool-dispatch time."""
    now = now or datetime.now(timezone.utc)
    identity = _lock_identity(
        db,
        context.org_id,
        context.workspace_id,
        context.machine_identity_id,
        now,
    )
    session = _lock_session(
        db,
        org_id=context.org_id,
        workspace_id=context.workspace_id,
        identity_id=identity.id,
        session_id=context.session_id,
        now=now,
    )
    credential = (
        db.query(MachineSessionCredential)
        .filter_by(
            id=context.credential_id,
            org_id=context.org_id,
            workspace_id=context.workspace_id,
            machine_identity_id=identity.id,
            session_id=session.id,
        )
        .with_for_update()
        .first()
    )
    if (
        credential is None
        or credential.revoked_at is not None
        or _as_utc(credential.expires_at) <= now
    ):
        raise _unauthorized()
    return MachinePrincipal(identity=identity), session


def close_agent_session(
    db: Session,
    principal: MachinePrincipal,
    *,
    session_id: str,
    status: str = "closed",
    reason_code: str = "SESSION_CLOSED",
    now: datetime | None = None,
) -> AgentSession:
    """Close or cancel a session and atomically revoke all its bearer credentials."""
    if status not in {"closed", "cancelled", "expired"}:
        raise ValueError("Unsupported agent session terminal status.")
    now = now or datetime.now(timezone.utc)
    identity = _lock_identity(
        db,
        principal.identity.org_id,
        principal.identity.workspace_id,
        principal.identity.id,
        now,
    )
    session = (
        db.query(AgentSession)
        .filter_by(
            id=session_id,
            org_id=identity.org_id,
            workspace_id=identity.workspace_id,
            machine_identity_id=identity.id,
        )
        .with_for_update()
        .first()
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Agent session not found.")
    changed = session.status == "active"
    if changed:
        session.status = status
        session.ended_at = now
    revoke_session_credentials_for_session(
        db, session, reason_code=reason_code, now=now
    )
    if changed:
        record_event(
            db,
            identity.org_id,
            None,
            f"agent_session.{status}",
            "agent_session",
            session.id,
            identity.workspace_id,
            {
                "machine_identity_id": identity.id,
                "reason_code": reason_code[:80],
            },
        )
    db.commit()
    return session
