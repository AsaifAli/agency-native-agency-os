import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

APP_URL = os.getenv("AGENCY_OS_TEST_RLS_DATABASE_URL")
WORKER_URL = os.getenv("AGENCY_OS_TEST_RLS_WORKER_DATABASE_URL")


def _engine(url):
    if not url:
        pytest.skip("dedicated PostgreSQL role URL is not configured")
    return create_engine(url, pool_pre_ping=True)


def test_app_can_only_authenticate_credentials_through_the_database_function():
    engine = _engine(APP_URL)
    try:
        with engine.connect() as connection:
            privileges = connection.execute(text("""
                SELECT
                    has_table_privilege(current_user, 'public.machine_session_credentials', 'SELECT'),
                    has_function_privilege(
                        current_user,
                        'agency_os_private.authenticate_mcp_session_credential(text,text,integer)',
                        'EXECUTE'
                    )
            """)).one()
            assert tuple(privileges) == (False, True)
            with pytest.raises(DBAPIError):
                connection.execute(text(
                    "SELECT * FROM public.machine_session_credentials LIMIT 1"
                ))
            connection.rollback()
            rows = connection.execute(text("""
                SELECT * FROM agency_os_private.authenticate_mcp_session_credential(
                    :credential_id, :token_hash, 120
                )
            """), {
                "credential_id": "a1b2c3d4-e5f6-4789-9012-1234567890ab",
                "token_hash": "0" * 64,
            }).all()
            assert rows == []
            connection.commit()
    finally:
        engine.dispose()


def test_worker_can_insert_only_through_execution_rls_and_cannot_authenticate():
    engine = _engine(WORKER_URL)
    try:
        with engine.connect() as connection:
            privileges = connection.execute(text("""
                SELECT
                    has_table_privilege(current_user, 'public.machine_session_credentials', 'SELECT'),
                    has_table_privilege(current_user, 'public.machine_session_credentials', 'INSERT'),
                    has_table_privilege(current_user, 'public.machine_session_credentials', 'UPDATE'),
                    has_table_privilege(current_user, 'public.machine_session_credentials', 'DELETE'),
                    has_function_privilege(
                        current_user,
                        'agency_os_private.authenticate_mcp_session_credential(text,text,integer)',
                        'EXECUTE'
                    )
            """)).one()
            assert tuple(privileges) == (False, True, False, False, False)
            with pytest.raises(DBAPIError):
                connection.execute(text(
                    "SELECT * FROM public.machine_session_credentials LIMIT 1"
                ))
            connection.rollback()
            with pytest.raises(DBAPIError):
                connection.execute(text("""
                    SELECT * FROM agency_os_private.authenticate_mcp_session_credential(
                        :credential_id, :token_hash, 120
                    )
                """), {
                    "credential_id": "a1b2c3d4-e5f6-4789-9012-1234567890ab",
                    "token_hash": "0" * 64,
                })
            connection.rollback()
    finally:
        engine.dispose()
