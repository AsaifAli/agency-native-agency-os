from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session
from app.config import settings
from app.db import get_db
from app.models import User, Membership, Role

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

def get_principal(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> Principal:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Bearer token required")
    email = _decode_token(authorization.removeprefix("Bearer ").strip())
    user = db.query(User).filter(User.email == email, User.active.is_(True)).first()
    if not user:
        raise HTTPException(401, "Unknown or inactive user")
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

def issue_access_token(email: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": email.lower(), "iss": settings.jwt_issuer, "aud": "agency-os-api",
         "iat": now, "exp": now + timedelta(minutes=30)},
        settings.jwt_secret, algorithm="HS256"
    )
