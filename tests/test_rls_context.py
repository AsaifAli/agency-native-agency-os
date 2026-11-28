from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import pytest

from app.db import set_rls_context, verify_postgres_role


def test_rls_context_is_persisted_on_session_and_is_transaction_local():
    engine = create_engine("sqlite://")
    db = sessionmaker(bind=engine)()
    try:
        set_rls_context(db, user_id="user-a")
        assert db.info["agency_os_rls_context"] == {
            "user_id": "user-a", "machine_org_id": "",
            "machine_workspace_id": "", "machine_identity_lookup_id": "",
        "browser_session_token_hash": "",
        }
    finally:
        db.close(); engine.dispose()


def test_rls_context_cannot_leak_between_sessions():
    engine = create_engine("sqlite://")
    factory = sessionmaker(bind=engine)
    first, second = factory(), factory()
    try:
        set_rls_context(first, user_id="user-a")
        set_rls_context(second, machine_org_id="org-b", machine_workspace_id="ws-b")
        assert first.info["agency_os_rls_context"]["user_id"] == "user-a"
        assert first.info["agency_os_rls_context"]["machine_org_id"] == ""
        assert second.info["agency_os_rls_context"]["user_id"] == ""
        assert second.info["agency_os_rls_context"]["machine_org_id"] == "org-b"
    finally:
        first.close(); second.close(); engine.dispose()


def test_postgres_role_verification_fails_closed_for_non_postgres_engine():
    engine = create_engine("sqlite://")
    try:
        with pytest.raises(RuntimeError, match="requires PostgreSQL"):
            verify_postgres_role(engine, expected_bypassrls=False, require_rls=True, expected_role="agency_os_app")
    finally:
        engine.dispose()


def test_required_rls_inventory_covers_every_tenant_table_and_execution_attempts():
    from app.db import REQUIRED_RLS_TABLES

    # Keep this aligned with the current explicit inventory. Outcome tables
    # were added in the RAAS capability migration.
    assert len(REQUIRED_RLS_TABLES) == 59
    assert {"project_outcomes", "outcome_measurements"}.issubset(REQUIRED_RLS_TABLES)
    assert {
        "organizations",
        "workspaces",
        "memberships",
        "founder_authorities",
        "browser_sessions",
        "machine_identities",
        "agent_sessions",
        "executions",
        "execution_attempts",
        "tool_invocations",
        "outbox_events",
        "orchestration_plan_delegations",
    }.issubset(REQUIRED_RLS_TABLES)


def test_required_rls_inventory_has_no_duplicate_table_names():
    from app.db import REQUIRED_RLS_TABLES

    assert len(REQUIRED_RLS_TABLES) == len(set(REQUIRED_RLS_TABLES))



def test_postgres_role_verification_requires_an_exact_expected_role():
    engine = create_engine("sqlite://")
    try:
        with pytest.raises(ValueError, match="expected_role"):
            verify_postgres_role(
                engine, expected_bypassrls=False, require_rls=True,
                expected_role=" ",
            )
    finally:
        engine.dispose()
