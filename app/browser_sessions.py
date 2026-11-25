"""Persistent, revocable browser authentication sessions."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.db import set_rls_context
from app.models import Membership, User
from app.audit import record_event
from app.jwt_keys import decode_jwt, encode_jwt
from app.security_models import BrowserSession


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _token_hash(jti: str) -> str:
    return hashlib.sha256(jti.encode("utf-8")).hexdigest()


def _decode_claims(token: str) -> dict:
    try:
        claims = decode_jwt(
            token, issuer=settings.jwt_issuer, audience="agency-os-api",
            options={"require": ["sub", "iss", "aud", "exp", "iat", "jti"]},
            leeway=30,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "Invalid or expired browser session") from exc
    if not isinstance(claims.get("jti"), str) or len(claims["jti"]) < 32:
        raise HTTPException(401, "Invalid or expired browser session")
    return claims


def issue_browser_session(db: Session, user: User, *, ttl_seconds: int) -> str:
    """Create a signed browser token and persist its one-way session identifier."""
    if not 300 <= ttl_seconds <= 43200:
        raise ValueError("Browser session TTL must be between 300 and 43200 seconds")
    now = _utcnow()
    jti = secrets.token_urlsafe(32)
    expires_at = now + timedelta(seconds=ttl_seconds)
    token = encode_jwt({
        "sub": user.email.lower(),
        "iss": settings.jwt_issuer,
        "aud": "agency-os-api",
        "iat": now,
        "exp": expires_at,
        "jti": jti,
    })
    db.add(
        BrowserSession(
            user_id=user.id,
            token_hash=_token_hash(jti),
            expires_at=expires_at,
        )
    )
    db.flush()
    return token


def authenticate_browser_session(db: Session, token: str) -> BrowserSession:
    claims = _decode_claims(token)
    token_hash = _token_hash(claims["jti"])
    set_rls_context(db, browser_session_token_hash=token_hash)
    session = db.query(BrowserSession).filter_by(token_hash=token_hash).first()
    now = _utcnow()
    if (
        session is None
        or session.revoked_at is not None
        or _aware(session.expires_at) <= now
    ):
        raise HTTPException(401, "Invalid or revoked browser session")
    set_rls_context(db, user_id=session.user_id)
    return session


def revoke_browser_session(db: Session, token: str) -> BrowserSession | None:
    """Revoke one browser session; repeated logout calls are safe and idempotent."""
    try:
        claims = _decode_claims(token)
    except HTTPException:
        return None
    token_hash = _token_hash(claims["jti"])
    set_rls_context(db, browser_session_token_hash=token_hash)
    session = db.query(BrowserSession).filter_by(token_hash=token_hash).first()
    if session is None or session.revoked_at is not None:
        return None
    session.revoked_at = _utcnow()
    set_rls_context(db, user_id=session.user_id)
    return session


def rotate_browser_session(
    db: Session, token: str, *, ttl_seconds: int
) -> tuple[BrowserSession, BrowserSession, str]:
    """Atomically revoke one live session and issue its replacement.

    The row lock serializes concurrent refresh attempts on PostgreSQL. The
    caller owns the transaction and must commit the revocation and replacement
    together before returning the replacement cookie to the browser.
    """
    claims = _decode_claims(token)
    token_hash = _token_hash(claims["jti"])
    set_rls_context(db, browser_session_token_hash=token_hash)
    old_session = (
        db.query(BrowserSession)
        .filter_by(token_hash=token_hash)
        .with_for_update()
        .first()
    )
    now = _utcnow()
    if (
        old_session is None
        or old_session.revoked_at is not None
        or _aware(old_session.expires_at) <= now
    ):
        raise HTTPException(401, "Invalid or revoked browser session")

    user = db.query(User).filter(User.id == old_session.user_id, User.active.is_(True)).first()
    if user is None or user.email.lower() != str(claims["sub"]).lower():
        raise HTTPException(401, "Unknown, inactive, or revoked user session")

    old_session.revoked_at = now
    set_rls_context(db, user_id=old_session.user_id)
    new_token = issue_browser_session(db, user, ttl_seconds=ttl_seconds)
    new_session = authenticate_browser_session(db, new_token)
    return old_session, new_session, new_token


def prune_expired_browser_sessions(
    db: Session, *, retention_days: int = 30, limit: int = 500
) -> int:
    """Delete bounded expired/revoked sessions after the configured retention window.

    Audit a metadata-only deletion event per organization before removing each
    row. Caller owns the transaction; worker uses the dedicated maintenance role.
    """
    if not 1 <= retention_days <= 3650:
        raise ValueError("retention_days must be between 1 and 3650")
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    cutoff = _utcnow() - timedelta(days=retention_days)
    rows = (
        db.query(BrowserSession)
        .filter(or_(
            BrowserSession.expires_at <= cutoff,
            BrowserSession.revoked_at <= cutoff,
        ))
        .order_by(BrowserSession.created_at.asc(), BrowserSession.id.asc())
        .with_for_update(skip_locked=True)
        .limit(limit)
        .all()
    )
    for session in rows:
        org_ids = [row[0] for row in db.query(Membership.org_id).filter_by(user_id=session.user_id).all()]
        for org_id in org_ids:
            record_event(
                db, org_id, None, "auth.browser_session_pruned",
                "browser_session", session.id,
                payload={"reason_code": "SESSION_RETENTION_ELAPSED"},
            )
        db.delete(session)
    if rows:
        db.flush()
    return len(rows)
