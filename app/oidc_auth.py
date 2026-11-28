"""Authentik OIDC relying-party integration and browser CSRF helpers."""
from __future__ import annotations

import hmac
import re
from urllib.parse import urlparse

from fastapi import HTTPException
from sqlalchemy.orm import Session
from authlib.integrations.starlette_client import OAuth

from app.config import settings
from app.db import set_rls_context
from app.models import Membership, User

_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

oauth = OAuth()


def verified_identity(claims: dict, required_acr: str = "") -> tuple[str, str]:
    subject = str(claims.get("sub") or "").strip()
    email = str(claims.get("email") or "").strip().lower()
    email_verified = claims.get("email_verified") is True or str(claims.get("email_verified")).lower() == "true"
    if not subject or len(subject) > 255 or not email_verified or not _EMAIL.fullmatch(email):
        raise HTTPException(status_code=401, detail="Identity provider did not return a verified account identity")
    if required_acr and claims.get("acr") != required_acr:
        raise HTTPException(status_code=403, detail="Required multi-factor authentication assurance was not satisfied")
    return subject, email


def validate_csrf_pair(cookie: str | None, header: str | None) -> None:
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise HTTPException(status_code=403, detail="CSRF validation failed")


def oidc_enabled() -> bool:
    return bool(settings.oidc_issuer and settings.oidc_client_id and settings.oidc_client_secret)


def oidc_client():
    if not oidc_enabled():
        raise HTTPException(status_code=503, detail="Authentik OIDC is not configured")
    return oauth.create_client("authentik")


def configure_oidc() -> None:
    if not oidc_enabled():
        return
    issuer = settings.oidc_issuer
    parsed = urlparse(issuer)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RuntimeError("OIDC_ISSUER must be an HTTPS issuer URL without credentials, query or fragment")
    if parsed.hostname.lower() in {"localhost", "127.0.0.1", "::1", "169.254.169.254"}:
        raise RuntimeError("OIDC_ISSUER cannot target a loopback or cloud metadata host")
    oauth.register(
        name="authentik",
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
        server_metadata_url=f"{issuer.rstrip('/')}/.well-known/openid-configuration",
        client_kwargs={
            "scope": "openid profile email",
            "code_challenge_method": "S256",
        },
    )


def link_provisioned_user(db: Session, issuer: str, subject: str, email: str) -> User:
    """Bind only a pre-provisioned active member; never JIT-create users or grants."""
    user = db.query(User).filter_by(oidc_issuer=issuer, oidc_subject=subject).first()
    if user is not None:
        if not user.active or user.email.lower() != email:
            raise HTTPException(status_code=403, detail="This identity is inactive or no longer matches its provisioned account")
    else:
        user = db.query(User).filter_by(email=email).with_for_update().first()
        if user is None or not user.active or user.oidc_subject or user.oidc_issuer:
            raise HTTPException(status_code=403, detail="This identity is not provisioned for Agency OS")
        user.oidc_issuer = issuer
        user.oidc_subject = subject
        db.flush()

    # The OIDC assertion has already been verified by the callback. Establish
    # the matched user's transaction-local identity before checking membership;
    # the PostgreSQL membership RLS policy intentionally hides rows otherwise.
    set_rls_context(db, user_id=user.id)
    if not db.query(Membership.id).filter_by(user_id=user.id).first():
        raise HTTPException(status_code=403, detail="This identity has no active organization membership")
    return user
