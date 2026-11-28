"""Short-lived bearer credentials bound to one Agency OS AgentSession."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import set_rls_context
from app.machine_identity import MachinePrincipal
from app.security_models import AgentSession, MachineIdentity, MachineSessionCredential

_TOKEN_PREFIX = "aos_ms_"
_SECRET_RE = re.compile(r"^[A-Za-z0-9_-]{40,64}$")
_ID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")
_ALLOWED_DATA_CLASSES = {"synthetic", "public"}


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
    token_hash: str


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _unauthorized() -> HTTPException:
    return HTTPException(status_code=401, detail="Invalid or expired session credential.")


def issue_session_credential(
    db: Session,
    principal: MachinePrincipal,
    *,
    session_id: str,
    ttl_seconds: int = 900,
    now: datetime | None = None,
) -> IssuedSessionCredential:
    """Create one short-lived credential under the caller's live execution transaction."""
    now = now or datetime.now(timezone.utc)
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or not 60 <= ttl_seconds <= 3600:
        raise HTTPException(status_code=422, detail="Session credential TTL must be between 60 and 3600 seconds.")

    identity = (
        db.query(MachineIdentity)
        .filter_by(
            id=principal.identity.id,
            org_id=principal.identity.org_id,
            workspace_id=principal.identity.workspace_id,
        )
        .with_for_update()
        .first()
    )
    if identity is None or identity.revoked_at is not None or _utc(identity.expires_at) <= now:
        raise _unauthorized()

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
    if (
        session is None
        or session.status != "active"
        or _utc(session.expires_at) <= now
        or session.data_class not in _ALLOWED_DATA_CLASSES
        or session.data_class not in identity.allowed_data_classes
    ):
        raise HTTPException(status_code=403, detail="Session credential is not permitted by OS policy.")

    # One credential per session for the first release. Rotation requires an
    # explicit provider Vault cleanup protocol and is deliberately not implicit.
    # A unique (workspace, session, version) constraint makes issuance one-shot.
    credential_id = secrets.token_hex(16)
    credential_id = f"{credential_id[:8]}-{credential_id[8:12]}-{credential_id[12:16]}-{credential_id[16:20]}-{credential_id[20:32]}"
    secret = secrets.token_urlsafe(32)
    token = f"{_TOKEN_PREFIX}{credential_id}.{secret}"
    expires_at = min(now + timedelta(seconds=ttl_seconds), _utc(session.expires_at), _utc(identity.expires_at))
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
        credential_version=1,
        expires_at=expires_at,
        request_window_started_at=now,
        request_count_window=0,
    )
    db.add(credential)
    db.flush()
    from app.audit import record_event
    record_event(
        db, identity.org_id, None, "machine_session_credential.issued",
        "machine_session_credential", credential.id, identity.workspace_id,
    )
    return IssuedSessionCredential(
        credential_id=credential.id, token=token, expires_at=expires_at, credential_version=1,
    )


def _parse_bearer(authorization: str | None) -> tuple[str, str, str]:
    if not isinstance(authorization, str):
        raise _unauthorized()
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token.startswith(_TOKEN_PREFIX):
        raise _unauthorized()
    credential_id, separator, secret = token[len(_TOKEN_PREFIX):].partition(".")
    if not separator or not _ID_RE.fullmatch(credential_id) or not _SECRET_RE.fullmatch(secret):
        raise _unauthorized()
    return credential_id, secret, hashlib.sha256(secret.encode("utf-8")).hexdigest()


def authenticate_session_credential(
    db: Session,
    authorization: str | None,
    *,
    requests_per_minute: int = 120,
) -> SessionCredentialContext:
    """Authenticate via a narrowly granted SECURITY DEFINER function on PostgreSQL."""
    credential_id, _secret, token_hash = _parse_bearer(authorization)
    if db.get_bind().dialect.name == "postgresql":
        row = db.execute(
            text("""
                SELECT auth_status, org_id, workspace_id, machine_identity_id,
                       session_id, credential_id
                FROM agency_os_private.authenticate_mcp_session_credential(
                    :credential_id, :token_hash, :request_limit
                )
            """),
            {
                "credential_id": credential_id,
                "token_hash": token_hash,
                "request_limit": requests_per_minute,
            },
        ).mappings().first()
        if row is None:
            db.rollback()
            raise _unauthorized()
        if row["auth_status"] == "rate_limited":
            db.commit()
            raise HTTPException(status_code=429, detail="Session request limit exceeded.")
        if row["auth_status"] != "ok":
            db.rollback()
            raise _unauthorized()
        context = SessionCredentialContext(
            org_id=row["org_id"], workspace_id=row["workspace_id"],
            machine_identity_id=row["machine_identity_id"], session_id=row["session_id"],
            credential_id=row["credential_id"], token_hash=token_hash,
        )
    else:
        now = datetime.now(timezone.utc)
        credential = db.query(MachineSessionCredential).filter_by(id=credential_id).with_for_update().first()
        if credential is None or not hmac.compare_digest(credential.token_hash, token_hash):
            raise _unauthorized()
        identity = db.query(MachineIdentity).filter_by(
            id=credential.machine_identity_id, org_id=credential.org_id,
            workspace_id=credential.workspace_id,
        ).with_for_update().first()
        session = db.query(AgentSession).filter_by(
            id=credential.session_id, org_id=credential.org_id,
            workspace_id=credential.workspace_id, machine_identity_id=credential.machine_identity_id,
        ).with_for_update().first()
        if (
            credential.revoked_at is not None or _utc(credential.expires_at) <= now
            or identity is None or identity.revoked_at is not None or _utc(identity.expires_at) <= now
            or session is None or session.status != "active" or _utc(session.expires_at) <= now
            or session.data_class not in _ALLOWED_DATA_CLASSES
        ):
            raise _unauthorized()
        window = credential.request_window_started_at
        if window is None or (now - _utc(window)).total_seconds() >= 60:
            credential.request_window_started_at = now
            credential.request_count_window = 0
        if credential.request_count_window >= max(1, requests_per_minute):
            db.commit()
            raise HTTPException(status_code=429, detail="Session request limit exceeded.")
        credential.request_count_window += 1
        credential.last_used_at = now
        identity.last_used_at = now
        session.last_seen_at = now
        context = SessionCredentialContext(
            org_id=identity.org_id, workspace_id=identity.workspace_id,
            machine_identity_id=identity.id, session_id=session.id,
            credential_id=credential.id, token_hash=token_hash,
        )
    set_rls_context(
        db, machine_org_id=context.org_id, machine_workspace_id=context.workspace_id,
    )
    db.commit()
    return context


def load_active_session_context(
    db: Session,
    context: SessionCredentialContext,
) -> tuple[MachinePrincipal, AgentSession]:
    """Revalidate credential, identity and session at every tool-dispatch boundary."""
    set_rls_context(
        db, machine_org_id=context.org_id, machine_workspace_id=context.workspace_id,
    )
    if db.get_bind().dialect.name == "postgresql":
        active = db.execute(
            text("""
                SELECT agency_os_private.is_mcp_session_credential_active(
                    :credential_id, :token_hash, :org_id, :workspace_id,
                    :machine_identity_id, :session_id
                )
            """),
            {
                "credential_id": context.credential_id,
                "token_hash": context.token_hash,
                "org_id": context.org_id,
                "workspace_id": context.workspace_id,
                "machine_identity_id": context.machine_identity_id,
                "session_id": context.session_id,
            },
        ).scalar_one()
        if active is not True:
            raise _unauthorized()
    identity = db.query(MachineIdentity).filter_by(
        id=context.machine_identity_id, org_id=context.org_id, workspace_id=context.workspace_id,
    ).with_for_update().first()
    session = db.query(AgentSession).filter_by(
        id=context.session_id, org_id=context.org_id, workspace_id=context.workspace_id,
        machine_identity_id=context.machine_identity_id,
    ).with_for_update().first()
    now = datetime.now(timezone.utc)
    if (
        identity is None or identity.revoked_at is not None or _utc(identity.expires_at) <= now
        or session is None or session.status != "active" or _utc(session.expires_at) <= now
        or session.data_class not in _ALLOWED_DATA_CLASSES
    ):
        raise _unauthorized()
    return MachinePrincipal(identity=identity), session
