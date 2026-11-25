from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.db import Base
from app.models import Organization, User, Membership, Role, AuditEvent
from app.security_models import BrowserSession
from app.auth import get_principal
from app.browser_sessions import (
    authenticate_browser_session,
    issue_browser_session,
    revoke_browser_session,
    rotate_browser_session,
    prune_expired_browser_sessions,
)


@pytest.fixture
def browser_db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(
        engine,
        tables=[Organization.__table__, User.__table__, Membership.__table__, BrowserSession.__table__, AuditEvent.__table__],
    )
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = factory()
    user = User(email="founder@example.com", display_name="Founder", active=True)
    org = Organization(name="Browser Session Org")
    db.add_all([user, org])
    db.flush()
    db.add(Membership(org_id=org.id, user_id=user.id, role=Role.owner))
    db.commit()
    try:
        yield db, user
    finally:
        db.close()
        engine.dispose()


def test_browser_session_persists_only_a_digest_and_authenticates(browser_db):
    db, user = browser_db
    token = issue_browser_session(db, user, ttl_seconds=600)
    db.commit()

    claims = jwt.decode(
        token, settings.jwt_secret, algorithms=["HS256"],
        issuer=settings.jwt_issuer, audience="agency-os-api",
    )
    row = db.query(BrowserSession).one()
    assert claims["jti"]
    assert row.token_hash != claims["jti"]
    assert len(row.token_hash) == 64
    assert row.user_id == user.id
    assert authenticate_browser_session(db, token).id == row.id


def test_browser_session_replay_is_rejected_after_logout(browser_db):
    db, user = browser_db
    token = issue_browser_session(db, user, ttl_seconds=600)
    db.commit()

    assert revoke_browser_session(db, token) is not None
    db.commit()
    with pytest.raises(HTTPException) as error:
        authenticate_browser_session(db, token)
    assert error.value.status_code == 401


def test_browser_session_expiry_is_enforced_from_persistent_record(browser_db):
    db, user = browser_db
    token = issue_browser_session(db, user, ttl_seconds=600)
    db.commit()
    row = db.query(BrowserSession).one()
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()

    with pytest.raises(HTTPException) as error:
        authenticate_browser_session(db, token)
    assert error.value.status_code == 401


def test_browser_session_rejects_inactive_user(browser_db):
    db, user = browser_db
    token = issue_browser_session(db, user, ttl_seconds=600)
    db.commit()
    user.active = False
    db.commit()

    with pytest.raises(HTTPException) as error:
        get_principal(authorization=None, session_cookie=token, db=db)
    assert error.value.status_code == 401


def test_get_principal_accepts_persisted_browser_cookie(browser_db):
    db, user = browser_db
    token = issue_browser_session(db, user, ttl_seconds=600)
    db.commit()

    principal = get_principal(authorization=None, session_cookie=token, db=db)
    assert principal.user.id == user.id


def test_browser_session_rejects_token_without_jti(browser_db):
    db, user = browser_db
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {"sub": user.email, "iss": settings.jwt_issuer, "aud": "agency-os-api",
         "iat": now, "exp": now + timedelta(minutes=5)},
        settings.jwt_secret, algorithm="HS256",
    )
    with pytest.raises(HTTPException) as error:
        authenticate_browser_session(db, token)
    assert error.value.status_code == 401


def test_repeated_browser_session_revocation_is_idempotent(browser_db):
    db, user = browser_db
    token = issue_browser_session(db, user, ttl_seconds=600)
    db.commit()

    assert revoke_browser_session(db, token) is not None
    db.commit()
    assert revoke_browser_session(db, token) is None


def test_logout_revokes_cookie_and_prevents_replay(browser_db):
    from fastapi.testclient import TestClient
    from app.db import get_db
    from app.main import app
    from app.config import settings

    db, user = browser_db
    token = issue_browser_session(db, user, ttl_seconds=600)
    db.commit()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        client.cookies.set(settings.oidc_session_cookie_name, token)
        client.cookies.set(settings.oidc_csrf_cookie_name, "csrf-test-value")
        headers = {
            "Origin": "http://localhost:3000",
            "X-CSRF-Token": "csrf-test-value",
        }
        assert client.get("/v1/auth/me").status_code == 200
        logged_out = client.post("/v1/auth/logout", headers=headers)
        assert logged_out.status_code == 200
        client.cookies.set(settings.oidc_session_cookie_name, token)
        replay = client.get("/v1/auth/me")
        assert replay.status_code == 401
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_revoked_browser_jwt_is_not_accepted_as_bearer_token(browser_db):
    db, user = browser_db
    token = issue_browser_session(db, user, ttl_seconds=600)
    db.commit()
    revoke_browser_session(db, token)
    db.commit()

    with pytest.raises(HTTPException) as error:
        get_principal(authorization=f"Bearer {token}", session_cookie=None, db=db)
    assert error.value.status_code == 401


def test_browser_session_rotation_revokes_old_and_issues_new(browser_db):
    db, user = browser_db
    old_token = issue_browser_session(db, user, ttl_seconds=600)
    db.commit()

    old_session, new_session, new_token = rotate_browser_session(
        db, old_token, ttl_seconds=600
    )
    db.commit()

    assert old_session.revoked_at is not None
    assert new_session.id != old_session.id
    assert authenticate_browser_session(db, new_token).id == new_session.id
    with pytest.raises(HTTPException) as error:
        authenticate_browser_session(db, old_token)
    assert error.value.status_code == 401


def test_refresh_endpoint_rotates_cookie_and_audits_replacement(browser_db):
    from fastapi.testclient import TestClient
    from app.db import get_db
    from app.main import app
    from app.config import settings

    db, user = browser_db
    old_token = issue_browser_session(db, user, ttl_seconds=600)
    db.commit()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        client.cookies.set(settings.oidc_session_cookie_name, old_token, domain="testserver.local", path="/")
        client.cookies.set(settings.oidc_csrf_cookie_name, "csrf-refresh-value", domain="testserver.local", path="/")
        headers = {
            "Origin": "http://localhost:3000",
            "X-CSRF-Token": "csrf-refresh-value",
        }
        refreshed = client.post("/v1/auth/refresh", headers=headers)
        assert refreshed.status_code == 200
        new_token = client.cookies.get(settings.oidc_session_cookie_name, domain="testserver.local", path="/")
        assert new_token and new_token != old_token
        csrf_set_cookie = next(value for key, value in refreshed.headers.multi_items() if key.lower() == "set-cookie" and value.startswith(f"{settings.oidc_csrf_cookie_name}="))
        assert "csrf-refresh-value" in csrf_set_cookie
        assert f"Max-Age={settings.oidc_session_ttl_seconds}" in csrf_set_cookie
        assert client.get("/v1/auth/me").status_code == 200

        client.cookies.set(settings.oidc_session_cookie_name, old_token, domain="testserver.local", path="/")
        assert client.get("/v1/auth/me").status_code == 401

        events = db.query(AuditEvent).filter_by(event_type="auth.browser_session_rotated").all()
        assert len(events) == 1
        assert events[0].payload["replacement_session_id"]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_browser_session_retention_prunes_old_rows_and_audits_deletion(browser_db):
    db, user = browser_db
    now = datetime.now(timezone.utc)
    old = BrowserSession(user_id=user.id, token_hash="a" * 64, expires_at=now - timedelta(days=31))
    recent = BrowserSession(user_id=user.id, token_hash="b" * 64, expires_at=now - timedelta(days=2))
    active = BrowserSession(user_id=user.id, token_hash="c" * 64, expires_at=now + timedelta(days=2))
    old_revoked = BrowserSession(user_id=user.id, token_hash="d" * 64,
        expires_at=now + timedelta(days=10), revoked_at=now - timedelta(days=31))
    db.add_all([old, recent, active, old_revoked]); db.commit()

    assert prune_expired_browser_sessions(db, retention_days=30, limit=10) == 2
    db.commit()
    remaining = {row.id for row in db.query(BrowserSession).all()}
    assert remaining == {recent.id, active.id}
    events = db.query(AuditEvent).filter_by(event_type="auth.browser_session_pruned").all()
    assert {event.resource_id for event in events} == {old.id, old_revoked.id}
    assert all(event.payload["reason_code"] == "SESSION_RETENTION_ELAPSED" for event in events)


def test_browser_session_retention_rejects_unbounded_or_invalid_limits(browser_db):
    db, _ = browser_db
    with pytest.raises(ValueError, match="retention_days"):
        prune_expired_browser_sessions(db, retention_days=0)
    with pytest.raises(ValueError, match="limit"):
        prune_expired_browser_sessions(db, limit=0)
