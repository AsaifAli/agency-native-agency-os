"""PostgreSQL checks for the shared user-directory privilege boundary."""
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.engine import make_url

APP_URL = os.getenv("AGENCY_OS_TEST_RLS_DATABASE_URL")
WORKER_URL = os.getenv("AGENCY_OS_TEST_RLS_WORKER_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not (APP_URL and WORKER_URL),
    reason="Dedicated API and worker PostgreSQL URLs are required",
)


def test_api_can_read_users_but_only_update_oidc_binding_columns():
    for url in (APP_URL, WORKER_URL):
        parsed = make_url(url)
        assert parsed.get_backend_name() == "postgresql"
        assert parsed.database == "agency_os_worker_test", (
            "Safety check: identity privilege tests may only use agency_os_worker_test"
        )

    engine = create_engine(APP_URL, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            privileges = connection.execute(text("""
                SELECT
                    has_table_privilege(current_user, 'public.users', 'SELECT'),
                    has_table_privilege(current_user, 'public.users', 'INSERT'),
                    has_table_privilege(current_user, 'public.users', 'UPDATE'),
                    has_table_privilege(current_user, 'public.users', 'DELETE'),
                    has_column_privilege(current_user, 'public.users', 'oidc_issuer', 'UPDATE'),
                    has_column_privilege(current_user, 'public.users', 'oidc_subject', 'UPDATE'),
                    has_column_privilege(current_user, 'public.users', 'email', 'UPDATE'),
                    has_column_privilege(current_user, 'public.users', 'display_name', 'UPDATE'),
                    has_column_privilege(current_user, 'public.users', 'active', 'UPDATE')
            """)).one()
            assert privileges == (True, False, False, False, True, True, False, False, False)
    finally:
        engine.dispose()


def test_worker_cannot_read_or_mutate_the_shared_user_directory():
    engine = create_engine(WORKER_URL, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            privileges = connection.execute(text("""
                SELECT
                    has_table_privilege(current_user, 'public.users', 'SELECT'),
                    has_table_privilege(current_user, 'public.users', 'INSERT'),
                    has_table_privilege(current_user, 'public.users', 'UPDATE'),
                    has_table_privilege(current_user, 'public.users', 'DELETE')
            """)).one()
            assert privileges == (False, False, False, False)
    finally:
        engine.dispose()


def test_api_can_link_oidc_subject_without_mutating_primary_identity_fields():
    admin_url = os.getenv("AGENCY_OS_TEST_RLS_ADMIN_DATABASE_URL")
    if not admin_url:
        pytest.skip("Dedicated migrator PostgreSQL URL is required for identity write test")
    for url in (admin_url, APP_URL):
        parsed = make_url(url)
        assert parsed.get_backend_name() == "postgresql"
        assert parsed.database == "agency_os_worker_test", (
            "Safety check: identity mutation tests may only use agency_os_worker_test"
        )

    admin_engine = create_engine(admin_url, pool_pre_ping=True)
    app_engine = create_engine(APP_URL, pool_pre_ping=True)
    user_id = str(uuid.uuid4())
    original_email = f"identity-boundary-{uuid.uuid4().hex}@example.test"
    try:
        with admin_engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO public.users (id, email, display_name, active)
                VALUES (:id, :email, 'Synthetic identity', true)
            """), {"id": user_id, "email": original_email})

        with app_engine.begin() as connection:
            result = connection.execute(text("""
                UPDATE public.users
                   SET oidc_issuer = 'https://auth.example.test',
                       oidc_subject = 'synthetic-subject'
                 WHERE id = :id
            """), {"id": user_id})
            assert result.rowcount == 1

        with pytest.raises(DBAPIError):
            with app_engine.begin() as connection:
                connection.execute(text("""
                    UPDATE public.users SET email = 'attacker@example.test' WHERE id = :id
                """), {"id": user_id})

        with admin_engine.connect() as connection:
            identity = connection.execute(text("""
                SELECT email, oidc_issuer, oidc_subject
                  FROM public.users WHERE id = :id
            """), {"id": user_id}).one()
            assert identity == (original_email, "https://auth.example.test", "synthetic-subject")
    finally:
        with admin_engine.begin() as connection:
            connection.execute(text("DELETE FROM public.users WHERE id = :id"), {"id": user_id})
        admin_engine.dispose()
        app_engine.dispose()
