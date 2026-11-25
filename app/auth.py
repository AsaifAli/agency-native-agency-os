from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import jwt
from fastapi import Cookie, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from app.config import settings
from app.db import get_db
from app.models import User, Membership, FounderAuthority, Role
from app.browser_sessions import authenticate_browser_session

@dataclass
class Principal:
    user: User

def _decode_token(token: str) -> str:
    if settings.dev_auth_enabled and settings.app_env != "production" and token.startswith("dev:"):
        return token[4:].lower()
    if settings.app_env == "production" and (
        settings.jwt_secret == "unsafe-development-secret-change-me" or len(settings.jwt_secret) < 32
    ):
        raise HTTPException(503, "Production JWT signing secret is not securely configured")
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer=settings.jwt_issuer,
            audience="agency-os-api",
            options={"require": ["sub", "iss", "aud", "exp", "iat"]},
            leeway=30,
        )
        return str(claims["sub"]).lower()
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired bearer token")

def get_principal(
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=settings.oidc_session_cookie_name),
    db: Session = Depends(get_db),
) -> Principal:
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        if settings.dev_auth_enabled and settings.app_env != "production" and token.startswith("dev:"):
            email = _decode_token(token)
            user = db.query(User).filter(User.email == email, User.active.is_(True)).first()
        else:
            browser_session = authenticate_browser_session(db, token)
            user = db.query(User).filter(
                User.id == browser_session.user_id,
                User.active.is_(True),
            ).first()
            if user is not None and user.email.lower() != _decode_token(token):
                user = None
    elif session_cookie:
        browser_session = authenticate_browser_session(db, session_cookie)
        user = db.query(User).filter(
            User.id == browser_session.user_id,
            User.active.is_(True),
        ).first()
        if user is not None and user.email.lower() != _decode_token(session_cookie):
            user = None
    else:
        raise HTTPException(401, "Authenticated session required")
    if not user:
        raise HTTPException(401, "Unknown, inactive, or revoked user session")
    return Principal(user=user)

def require_membership(org_id: str, principal: Principal, db: Session) -> Role:
    membership = db.query(Membership).filter_by(org_id=org_id, user_id=principal.user.id).first()
    if not membership:
        # Avoid disclosing whether an organization exists to non-members.
        raise HTTPException(404, "Organization not found")
    return membership.role

def require_role(role: Role, allowed: set[Role]):
    if role not in allowed:
        raise HTTPException(403, "Insufficient organization role")

def issue_access_token(email: str, ttl_seconds: int = 1800) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": email.lower(), "iss": settings.jwt_issuer, "aud": "agency-os-api",
         "iat": now, "exp": now + timedelta(seconds=ttl_seconds)},
        settings.jwt_secret, algorithm="HS256"
    )


def has_founder_authority(db: Session, org_id: str, user_id: str) -> bool:
    # A grant is effective only while the user is active and remains a member
    # of the organization. Authority is separate from the membership role.
    return (
        db.query(FounderAuthority.id)
        .join(User, User.id == FounderAuthority.user_id)
        .join(
            Membership,
            (Membership.user_id == FounderAuthority.user_id)
            & (Membership.org_id == FounderAuthority.org_id),
        )
        .filter(
            FounderAuthority.org_id == org_id,
            FounderAuthority.user_id == user_id,
            FounderAuthority.active.is_(True),
            User.active.is_(True),
        )
        .first()
        is not None
    )


def require_founder_authority(db: Session, org_id: str, user_id: str) -> None:
    """Require an explicit founder grant; Role.owner is deliberately insufficient."""
    if not has_founder_authority(db, org_id, user_id):
        raise HTTPException(403, "Explicit founder authority is required")
