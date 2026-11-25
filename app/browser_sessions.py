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
