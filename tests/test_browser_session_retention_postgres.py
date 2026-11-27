"""PostgreSQL integration tests for the bounded browser-session retention RPC."""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.models import AuditEvent, Membership, Organization, Role, User
from app.security_models import BrowserSession


def test_browser_session_retention_rpc_is_worker_only_bounded_and_audited():
    admin_url = os.getenv("AGENCY_OS_TEST_DATABASE_URL")
    app_url = os.getenv("AGENCY_OS_TEST_RLS_DATABASE_URL")
    worker_url = os.getenv("AGENCY_OS_TEST_RLS_WORKER_DATABASE_URL")
    if not all((admin_url, app_url, worker_url)):
        pytest.skip(
            "Set admin, app and worker PostgreSQL URLs for browser-session retention tests"
        )

    for url in (admin_url, app_url, worker_url):
        parsed = make_url(url)
        assert parsed.get_backend_name() == "postgresql"
        assert parsed.database == "agency_os_worker_test", (
            "Safety check: browser-session retention tests may only use agency_os_worker_test"
        )

    admin_engine = create_engine(admin_url, pool_pre_ping=True)
    app_engine = create_engine(app_url, pool_pre_ping=True)
    worker_engine = create_engine(worker_url, pool_pre_ping=True)
    suffix = uuid.uuid4().hex[:12]
    org = Organization(name=f"Browser retention {suffix}")
    user = User(email=f"browser-retention-{suffix}@example.test", display_name="Synthetic Retention User", active=True)
    now = datetime.now(timezone.utc)
    old_expired = BrowserSession(user_id="pending", token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        expires_at=now - timedelta(days=31))
    recent_expired = BrowserSession(user_id="pending", token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        expires_at=now - timedelta(days=2))
    active = BrowserSession(user_id="pending", token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        expires_at=now + timedelta(days=2))
    old_revoked = BrowserSession(user_id="pending", token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        expires_at=now + timedelta(days=10), revoked_at=now - timedelta(days=31))

    org_id = None
    user_id = None
    session_ids = {}

    try:
        with Session(admin_engine) as db:
            db.add_all([org, user])
            db.flush()
            org_id = org.id
            user_id = user.id
            db.add(Membership(org_id=org_id, user_id=user_id, role=Role.owner))
            for row in (old_expired, recent_expired, active, old_revoked):
                row.user_id = user_id
                db.add(row)
            db.flush()
            session_ids = {
                "old_expired": old_expired.id,
                "recent_expired": recent_expired.id,
                "active": active.id,
                "old_revoked": old_revoked.id,
            }
            db.commit()

        with app_engine.connect() as connection:
            can_execute = connection.execute(text("""
                SELECT has_function_privilege(
                    current_user,
                    'agency_os_private.prune_expired_browser_sessions(integer, integer)',
                    'EXECUTE'
                )
            """)).scalar_one()
            assert can_execute is False

        with worker_engine.begin() as connection:
            can_execute = connection.execute(text("""
                SELECT has_function_privilege(
                    current_user,
                    'agency_os_private.prune_expired_browser_sessions(integer, integer)',
                    'EXECUTE'
                )
            """)).scalar_one()
            assert can_execute is True
            table_privileges = connection.execute(text("""
                SELECT
                    has_table_privilege(current_user, 'public.browser_sessions', 'SELECT'),
                    has_table_privilege(current_user, 'public.browser_sessions', 'DELETE')
            """)).one()
            assert table_privileges == (False, False)
            deleted = connection.execute(text("""
                SELECT agency_os_private.prune_expired_browser_sessions(
                    :retention_days, :batch_size
                )
            """), {"retention_days": 30, "batch_size": 10}).scalar_one()
            assert deleted == 2

        with Session(admin_engine) as db:
            remaining = {
                row.id
                for row in db.query(BrowserSession).filter_by(user_id=user_id).all()
            }
            assert remaining == {session_ids["recent_expired"], session_ids["active"]}
            events = db.query(AuditEvent).filter_by(
                org_id=org_id, event_type="auth.browser_session_pruned"
            ).all()
            assert {event.resource_id for event in events} == {
                session_ids["old_expired"], session_ids["old_revoked"]
            }
            assert all(event.payload["reason_code"] == "SESSION_RETENTION_ELAPSED" for event in events)

        with pytest.raises(DBAPIError):
            with worker_engine.begin() as connection:
                connection.execute(text("""
                    SELECT agency_os_private.prune_expired_browser_sessions(0, 10)
                """))
    finally:
        # Isolated test admin is the trusted superuser used for cleanup.
        with admin_engine.begin() as connection:
            if org_id is not None:
                connection.execute(text("DELETE FROM public.audit_events WHERE org_id = :org"), {"org": org_id})
                connection.execute(text("DELETE FROM public.browser_sessions WHERE user_id = :user"), {"user": user_id})
                connection.execute(text("DELETE FROM public.memberships WHERE org_id = :org AND user_id = :user"), {"org": org_id, "user": user_id})
                connection.execute(text("DELETE FROM public.organizations WHERE id = :org"), {"org": org_id})
                connection.execute(text("DELETE FROM public.users WHERE id = :user"), {"user": user_id})
        for engine in (admin_engine, app_engine, worker_engine):
            engine.dispose()
