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


def test_app_can_use_exact_lookup_function_but_cannot_read_credential_table():
    engine = _engine(APP_URL)
    try:
        with engine.connect() as connection:
            with pytest.raises(DBAPIError):
                connection.execute(text(
                    "SELECT * FROM public.agent_session_credentials LIMIT 1"
                ))
            connection.rollback()
            rows = connection.execute(text("""
                SELECT * FROM agency_os_private.lookup_agent_session_credential(
                    :session_id, :token_hash
                )
            """), {
                "session_id": "a1b2c3d4-e5f6-4789-9012-1234567890ab",
                "token_hash": "0" * 64,
            }).all()
            assert rows == []
    finally:
        engine.dispose()


def test_worker_cannot_read_credentials_or_use_app_authentication_lookup():
    engine = _engine(WORKER_URL)
    try:
        with engine.connect() as connection:
            with pytest.raises(DBAPIError):
                connection.execute(text(
                    "SELECT * FROM public.agent_session_credentials LIMIT 1"
                ))
            connection.rollback()
            with pytest.raises(DBAPIError):
                connection.execute(text("""
                    SELECT * FROM agency_os_private.lookup_agent_session_credential(
                        :session_id, :token_hash
                    )
                """), {
                    "session_id": "a1b2c3d4-e5f6-4789-9012-1234567890ab",
                    "token_hash": "0" * 64,
                })
            connection.rollback()
    finally:
        engine.dispose()


def test_worker_session_credential_creation_requires_live_execution_capability():
    engine = _engine(WORKER_URL)
    try:
        with engine.connect() as connection:
            with pytest.raises(DBAPIError):
                connection.execute(text("""
                    SELECT * FROM agency_os_private.create_agent_session_with_credential(
                        :execution_id, :session_id, :purpose, :data_class,
                        :ttl_seconds, :token_hash, :token_prefix
                    )
                """), {
                    "execution_id": "00000000-0000-4000-8000-000000000001",
                    "session_id": "a1b2c3d4-e5f6-4789-9012-1234567890ab",
                    "purpose": "Claude Managed Agents MCP session",
                    "data_class": "public",
                    "ttl_seconds": 900,
                    "token_hash": "0" * 64,
                    "token_prefix": "aos_sc_a1b2c3d4-e5f6-4789-9012-1234567890ab.",
                })
            connection.rollback()
    finally:
        engine.dispose()


def test_app_cannot_mint_or_revoke_worker_session_credentials():
    engine = _engine(APP_URL)
    try:
        with engine.connect() as connection:
            with pytest.raises(DBAPIError):
                connection.execute(text("""
                    SELECT * FROM agency_os_private.create_agent_session_with_credential(
                        :execution_id, :session_id, :purpose, :data_class,
                        :ttl_seconds, :token_hash, :token_prefix
                    )
                """), {
                    "execution_id": "00000000-0000-4000-8000-000000000001",
                    "session_id": "a1b2c3d4-e5f6-4789-9012-1234567890ab",
                    "purpose": "Claude Managed Agents MCP session",
                    "data_class": "public",
                    "ttl_seconds": 900,
                    "token_hash": "0" * 64,
                    "token_prefix": "aos_sc_a1b2c3d4-e5f6-4789-9012-1234567890ab.",
                })
            connection.rollback()
    finally:
        engine.dispose()
