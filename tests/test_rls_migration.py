import importlib.util
from pathlib import Path

from app.db import Base
import app.models  # noqa: F401
import app.domain_models  # noqa: F401
import app.operations_models  # noqa: F401
import app.security_models  # noqa: F401
import app.telephony.models  # noqa: F401
import app.outreach.models  # noqa: F401
import app.workforce_models  # noqa: F401

PATH = Path(__file__).parents[1] / "migrations/versions/t0a1b2c3d4e5_postgresql_tenant_row_level_security.py"
SPEC = importlib.util.spec_from_file_location("tenant_rls_migration", PATH)
MIGRATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MIGRATION)


def test_rls_migration_covers_every_model_table_with_org_id():
    expected = {t.name: "workspace_id" in {c.name for c in t.columns}
        for t in Base.metadata.sorted_tables if "org_id" in {c.name for c in t.columns}}
    # workspace_grants is introduced by the follow-up authorization migration;
    # the original migration remains an immutable historical baseline.
    expected.pop("workspace_grants")
    assert MIGRATION.ORG_TABLES == expected


def test_rls_migration_has_security_definer_membership_and_dedicated_roles():
    source = PATH.read_text()
    assert "SECURITY DEFINER" in source
    assert "agency_os_migrator" in source
    assert "agency_os_app" in source and "agency_os_worker" in source
    assert "REVOKE ALL ON FUNCTION" in source
    assert "FORCE ROW LEVEL SECURITY" in source
    assert "browser_session_isolation" in source
    assert "agency_os.browser_session_token_hash" in source


def test_machine_rls_context_is_workspace_scoped():
    source = PATH.read_text()
    assert "agency_os.machine_org_id" in source
    assert "agency_os.machine_workspace_id" in source
    assert "agency_os.machine_identity_lookup_id" in source
    assert "id = nullif(current_setting('agency_os.machine_workspace_id', true), '')" in source


def test_existing_database_role_bootstrap_transfers_old_object_ownership():
    source = (PATH.parents[2] / "docker/postgres/01-roles.sh").read_text()
    assert "REASSIGN OWNED BY agency_os TO agency_os_migrator" in source



def test_worker_followup_migration_removes_bypass_and_scopes_attempts():
    worker_migration = PATH.with_name(
        "u1b2c3d4e5f6_worker_nobypassrls_scope.py"
    ).read_text()
    role_bootstrap = (PATH.parents[2] / "docker/postgres/01-roles.sh").read_text()

    assert "worker_workspace_scopes" in worker_migration
    assert "SECURITY DEFINER" in worker_migration
    assert "execution_attempt_tenant_isolation" in worker_migration
    assert "session_user" in worker_migration and "agency_os_worker" in worker_migration
    assert "prune_expired_browser_sessions" in worker_migration
    assert "REVOKE ALL ON TABLE public.users" in worker_migration
    assert "REVOKE ALL ON TABLES FROM agency_os_worker" in worker_migration
    assert "REVOKE ALL ON SEQUENCES FROM agency_os_worker" in worker_migration
    assert "agency_os_worker" in role_bootstrap
    assert "ALTER ROLE agency_os_worker" in role_bootstrap
    assert "NOINHERIT NOBYPASSRLS;" in role_bootstrap
    assert "ALTER ROLE agency_os_migrator" in role_bootstrap
    assert "NOINHERIT BYPASSRLS;" in role_bootstrap


def test_startup_rls_inventory_matches_all_migration_tables():
    from app.db import REQUIRED_RLS_TABLES

    expected = set(MIGRATION.ORG_TABLES) | {
        "organizations",
        "browser_sessions",
        "execution_attempts",
    }
    assert REQUIRED_RLS_TABLES == expected | {"workspace_grants"}


def test_workspace_authorization_migration_uses_exact_grants_and_audited_functions():
    path = PATH.with_name("v2c4e6a8b0d2_human_workspace_authorization.py")
    source = path.read_text()
    assert "user_has_workspace_access" in source
    assert "workspace_grants" in source
    assert "revoked_at IS NULL" in source
    assert "grant_workspace_access" in source and "revoke_workspace_access" in source
    assert "workspace.access_granted" in source and "workspace.access_revoked" in source
    assert "agency_os.machine_workspace_id" in source
    assert "workspace_id IS NULL" in source
    assert "workspace_id IS NOT NULL" in source
    assert "agency_os_migrator" in source
    assert "REVOKE ALL ON FUNCTION" in source


def test_workspace_authorization_migration_covers_every_workspace_owned_table():
    path = PATH.with_name("v2c4e6a8b0d2_human_workspace_authorization.py")
    spec = importlib.util.spec_from_file_location("workspace_rls_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    expected = {
        table.name
        for table in Base.metadata.sorted_tables
        if {"org_id", "workspace_id"} <= {column.name for column in table.columns}
        and table.name != "workspace_grants"
    }
    assert set(migration.WORKSPACE_TABLES) == expected
