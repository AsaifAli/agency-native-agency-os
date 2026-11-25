"""Persistent, revocable browser authentication sessions."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.models import User
from app.security_models import BrowserSession


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _token_hash(jti: str) -> str:
    return hashlib.sha256(jti.encode("utf-8")).hexdigest()


def _decode_claims(token: str) -> dict:
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer=settings.jwt_issuer,
            audience="agency-os-api",
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
    token = jwt.encode(
        {
            "sub": user.email.lower(),
            "iss": settings.jwt_issuer,
            "aud": "agency-os-api",
            "iat": now,
            "exp": expires_at,
            "jti": jti,
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
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
    session = db.query(BrowserSession).filter_by(token_hash=_token_hash(claims["jti"])).first()
    now = _utcnow()
    if (
        session is None
        or session.revoked_at is not None
        or _aware(session.expires_at) <= now
    ):
        raise HTTPException(401, "Invalid or revoked browser session")
    return session


def revoke_browser_session(db: Session, token: str) -> BrowserSession | None:
    """Revoke one browser session; repeated logout calls are safe and idempotent."""
    try:
        claims = _decode_claims(token)
    except HTTPException:
        return None
    session = db.query(BrowserSession).filter_by(token_hash=_token_hash(claims["jti"])).first()
    if session is None or session.revoked_at is not None:
        return None
    session.revoked_at = _utcnow()
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
    old_session = (
        db.query(BrowserSession)
        .filter_by(token_hash=_token_hash(claims["jti"]))
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
    new_token = issue_browser_session(db, user, ttl_seconds=ttl_seconds)
    new_session = authenticate_browser_session(db, new_token)
    return old_session, new_session, new_token
