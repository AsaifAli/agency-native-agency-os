"""Regression tests for the worker-capability RLS policy cutover."""

import importlib.util
from pathlib import Path

import pytest


MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "migrations/versions/b1c3d5e7f9a2_restore_workspace_grants_after_worker_cutover.py"
)
SPEC = importlib.util.spec_from_file_location(
    "restore_workspace_grants_after_worker_cutover", MIGRATION_PATH
)
MIGRATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MIGRATION)


def test_followup_migration_is_ordered_after_worker_capability_cutover():
    assert MIGRATION.revision == "b1c3d5e7f9a2"
    assert MIGRATION.down_revision == "a7c2e9f4b1d6"


def test_human_rls_requires_exact_workspace_grant_except_explicit_org_rows():
    nullable_tables = {"audit_events", "outbox_events"}

    for table in MIGRATION.WORKSPACE_TABLES:
        predicate = MIGRATION.human_workspace_predicate(table)
        if table in nullable_tables:
            assert "workspace_id IS NULL" in predicate
            assert "user_has_org_access" in predicate
            assert "workspace_id IS NOT NULL" in predicate
            assert "user_has_workspace_access" in predicate
        else:
            assert "user_has_workspace_access" in predicate
            assert "user_has_org_access" not in predicate


def test_machine_rls_keeps_exact_scope_and_identity_lookup_exception():
    for table in MIGRATION.WORKSPACE_TABLES:
        predicate = MIGRATION.machine_workspace_predicate(table)
        assert "machine_org_id" in predicate
        if table == "outbox_events":
            assert "workspace_id IS NULL" in predicate
        elif table == "machine_identities":
            assert "machine_identity_lookup_id" in predicate
        else:
            assert "machine_workspace_id" in predicate


def test_worker_rls_uses_verified_capability_not_machine_gucs():
    for table in MIGRATION.WORKSPACE_TABLES:
        predicate = MIGRATION.worker_workspace_predicate(table)
        if table == "machine_identities":
            assert predicate == "FALSE"
        else:
            assert "session_user = 'agency_os_worker'" in predicate
            assert "worker_has_execution_context" in predicate
            assert "machine_org_id" not in predicate
            assert "machine_workspace_id" not in predicate


def test_workspace_and_attempt_policies_preserve_exact_human_scope():
    workspace_select = MIGRATION.workspace_select_predicate()
    assert "user_has_workspace_access" in workspace_select
    assert "user_has_org_access" not in workspace_select
    assert "worker_has_execution_context" in workspace_select

    attempts = MIGRATION.execution_attempt_predicate()
    assert "user_has_workspace_access" in attempts
    assert "user_has_org_access" not in attempts
    assert "worker_has_execution_context" in attempts


def test_workspace_write_policies_remain_founder_gated():
    policies = MIGRATION.workspace_write_policies()
    assert "workspace_insert" in policies
    assert "workspace_update" in policies
    assert "workspace_delete" in policies
    assert "user_has_org_access" in policies["workspace_insert"]
    assert "founder_authorities" in policies["workspace_update"]
    assert "founder_authorities" in policies["workspace_delete"]

def test_workspace_policy_inventory_matches_the_original_grant_migration():
    original_path = MIGRATION_PATH.with_name(
        "v2c4e6a8b0d2_human_workspace_authorization.py"
    )
    original_spec = importlib.util.spec_from_file_location(
        "original_human_workspace_authorization", original_path
    )
    original = importlib.util.module_from_spec(original_spec)
    original_spec.loader.exec_module(original)

    assert set(MIGRATION.WORKSPACE_TABLES) == set(original.WORKSPACE_TABLES)
    assert (
        MIGRATION.ORG_LEVEL_NULLABLE_WORKSPACE_TABLES
        == original.ORG_LEVEL_NULLABLE_WORKSPACE_TABLES
    )


def test_upgrade_emits_workspace_scoped_policies_and_keeps_worker_capabilities(monkeypatch):
    statements = []

    class _Dialect:
        name = "postgresql"

    class _Bind:
        dialect = _Dialect()

    class _Operations:
        @staticmethod
        def get_bind():
            return _Bind()

        @staticmethod
        def execute(statement):
            statements.append(str(statement))

    monkeypatch.setattr(MIGRATION, "op", _Operations)
    MIGRATION.upgrade()
    sql = "\\n".join(statements)

    task_policy = next(
        statement for statement in statements
        if 'CREATE POLICY tenant_isolation ON public."tasks"' in statement
    )
    assert "user_has_workspace_access" in task_policy
    assert "worker_has_execution_context" in task_policy
    assert "machine_workspace_id" in task_policy
    assert "user_has_org_access" not in task_policy

    audit_policy = next(
        statement for statement in statements
        if 'CREATE POLICY tenant_isolation ON public."audit_events"' in statement
    )
    assert "workspace_id IS NULL" in audit_policy
    assert "user_has_org_access" in audit_policy
    assert "user_has_workspace_access" in audit_policy

    assert "CREATE POLICY workspace_select" in sql
    assert "CREATE POLICY workspace_update" in sql
    assert "CREATE POLICY workspace_delete" in sql
    assert "CREATE POLICY execution_attempt_tenant_isolation" in sql

def test_outbox_worker_policy_requires_a_non_null_workspace():
    predicate = MIGRATION.worker_workspace_predicate("outbox_events")
    assert "workspace_id IS NOT NULL" in predicate
    assert "worker_has_execution_context" in predicate


def test_postgres_downgrade_refuses_to_restore_weaker_human_workspace_access(monkeypatch):
    class _Dialect:
        name = "postgresql"

    class _Bind:
        dialect = _Dialect()

    class _Operations:
        @staticmethod
        def get_bind():
            return _Bind()

    monkeypatch.setattr(MIGRATION, "op", _Operations)
    with pytest.raises(RuntimeError, match="Unsafe downgrade refused"):
        MIGRATION.downgrade()
