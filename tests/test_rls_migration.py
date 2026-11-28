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
import app.private_ops_models  # noqa: F401

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
    # Outcome tables were introduced by a later additive migration; keep the
    # original tenant-RLS revision immutable.
    expected.pop("project_outcomes", None)
    expected.pop("outcome_measurements", None)
    expected.pop("orchestration_plan_delegations", None)
    expected.pop("knowledge_items", None)
    expected.pop("business_drafts", None)
    expected.pop("learning_candidates", None)
    # Session credentials are protected by a dedicated execution-bound insert policy
    # and a SECURITY DEFINER authentication function, not the general tenant policy.
    expected.pop("machine_session_credentials", None)
    # Orchestration plan links receive tenant scope in a later additive
    # migration; keep the original tenant-RLS revision immutable.
    expected.pop("orchestration_plan_delegations", None)
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


def test_fresh_database_role_bootstrap_transfers_database_and_schema_ownership_safely():
    source = (PATH.parents[2] / "docker/postgres/01-roles.sh").read_text()
    assert "ALTER DATABASE agency_os OWNER TO agency_os_migrator" in source
    assert "ALTER SCHEMA public OWNER TO agency_os_migrator" in source
    assert "GRANT USAGE, CREATE ON SCHEMA public TO agency_os_migrator" in source
    # REASSIGN OWNED also processes shared/system-owned objects and breaks
    # initialization on a fresh PostgreSQL cluster; keep bootstrap narrowly scoped.
    assert "REASSIGN OWNED BY agency_os TO agency_os_migrator" not in source



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
        "organizations", "browser_sessions", "execution_attempts",
        "project_outcomes", "outcome_measurements",
        "orchestration_plan_delegations", "knowledge_items", "business_drafts",
        "machine_session_credentials", "learning_candidates",
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
    expected.difference_update({
        "project_outcomes", "outcome_measurements",
        "orchestration_plan_delegations", "knowledge_items", "business_drafts",
        "machine_session_credentials", "learning_candidates",
    })
    assert set(migration.WORKSPACE_TABLES) == expected


def test_only_explicit_org_level_tables_allow_null_workspace_rows():
    path = PATH.with_name("v2c4e6a8b0d2_human_workspace_authorization.py")
    spec = importlib.util.spec_from_file_location("workspace_rls_nullable_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    nullable = {
        table.name
        for table in Base.metadata.sorted_tables
        if "workspace_id" in table.c
        and table.c.workspace_id.nullable
        and table.name in migration.WORKSPACE_TABLES
    }
    assert nullable == set(migration.ORG_LEVEL_NULLABLE_WORKSPACE_TABLES)


def test_workspace_grant_migration_preserves_machine_scope_and_audits_backfill():
    path = PATH.with_name("v2c4e6a8b0d2_human_workspace_authorization.py")
    source = path.read_text()
    assert "JOIN public.memberships AS m ON m.org_id = w.org_id" in source
    assert "JOIN public.users AS u ON u.id = m.user_id" in source
    assert "WHERE u.active IS TRUE" in source
    assert "ON CONFLICT (org_id, workspace_id, user_id)" in source
    assert "GRANT EXECUTE ON FUNCTION" in source
    assert "TO agency_os_app, agency_os_worker" in source
    assert "agency_os.machine_identity_lookup_id" in source
    assert "workspace_id IS NULL" in source



def test_project_outcome_tables_are_added_to_current_rls_inventory():
    migration_path = PATH.with_name("ab2c3d4e5f6a_project_outcomes.py")
    source = migration_path.read_text()
    from app.db import REQUIRED_RLS_TABLES

    assert {"project_outcomes", "outcome_measurements"} <= REQUIRED_RLS_TABLES
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "FORCE ROW LEVEL SECURITY" in source
    assert "user_has_workspace_access" in source
    assert "outcome_measurements_append_only" in source
    assert "REVOKE UPDATE, DELETE" in source

def test_worker_global_workspace_enumerator_is_revoked_and_replaced_by_single_scope_claim():
    cutover = PATH.with_name(
        "a7c2e9f4b1d6_worker_rls_capability_cutover.py"
    ).read_text()
    maintenance = PATH.with_name(
        "e1f4a6b8c0d2_worker_workspace_maintenance_capabilities.py"
    ).read_text()
    return_type_fix = PATH.with_name(
        "f3b7d9e1a5c2_worker_maintenance_claim_return_type_fix.py"
    ).read_text()

    # The legacy SECURITY DEFINER inventory function may remain for historical
    # compatibility, but neither PUBLIC nor the worker role may execute it.
    assert "p.proname = 'worker_workspace_scopes'" in cutover
    assert "REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC, agency_os_worker" in cutover

    # Maintenance discovery is an atomic one-workspace claim with a short lease.
    assert "claim_worker_maintenance_scope" in maintenance
    assert "LIMIT 1" in maintenance
    assert "FOR UPDATE OF w SKIP LOCKED" in maintenance
    assert "p_lease_seconds NOT BETWEEN 15 AND 300" in maintenance
    assert "establish_worker_workspace_context" in maintenance
    assert "release_worker_maintenance_scope" in maintenance
    assert "GRANT EXECUTE ON FUNCTION agency_os_private.{signature} TO agency_os_worker" in maintenance

    # CREATE OR REPLACE must preserve the function ACL established by the
    # maintenance migration; this follow-up only corrects result casts.
    assert "CREATE OR REPLACE FUNCTION agency_os_private.claim_worker_maintenance_scope" in return_type_fix
    assert "GRANT EXECUTE" not in return_type_fix


def test_public_schema_cannot_be_used_for_object_injection_by_runtime_roles():
    migration = (PATH.parent / "d6f8a0b2c4e6_public_schema_runtime_lockdown.py").read_text()
    bootstrap = (PATH.parents[2] / "docker/postgres/01-roles.sh").read_text()

    assert "REVOKE CREATE ON SCHEMA public " in migration
    assert "FROM PUBLIC, agency_os_app, agency_os_worker" in migration
    assert "GRANT USAGE ON SCHEMA public TO agency_os_app, agency_os_worker" in migration
    assert "REVOKE CREATE ON SCHEMA public FROM PUBLIC, agency_os_app, agency_os_worker" in bootstrap


def test_worker_machine_identity_rls_is_execution_scoped_not_disabled():
    migration = PATH.with_name("e8a1c3d5f7b9_worker_execution_machine_identity_scope.py").read_text()
    assert "worker_has_execution_context" in migration
    assert "machine_identities.subject_id" in migration
    assert "e.agent_id" in migration
    assert "revoked_at IS NULL" in migration
    assert "expires_at > clock_timestamp()" in migration
    assert "e.machine_session_id" in migration
    assert "agency_os.machine_identity_lookup_id" in migration
    assert "CREATE POLICY tenant_isolation ON public.machine_identities" in migration


def test_private_operations_migration_enforces_workspace_rls_and_denies_worker_role():
    path = PATH.with_name("a7b2c9d4e1f6_private_operations_knowledge.py")
    source = path.read_text()
    assert '"knowledge_items"' in source and '"business_drafts"' in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "FORCE ROW LEVEL SECURITY" in source
    assert "user_has_workspace_access" in source
    assert "session_user <> 'agency_os_worker'" in source
    assert "TO agency_os_app" in source
    assert "REVOKE ALL ON public." in source and "FROM agency_os_worker" in source


def test_learning_candidate_migration_is_workspace_rls_protected_and_worker_denied():
    path = PATH.with_name("a1b2c3d4e5f6_workspace_learning_candidates.py")
    source = path.read_text()
    assert 'revision = "a1b2c3d4e5f6"' in source
    assert '"z6f1b3d8a2c5", "b7d4c9a2e6f1"' in source
    assert '"learning_candidates"' in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "FORCE ROW LEVEL SECURITY" in source
    assert "user_has_workspace_access" in source
    assert "session_user <> 'agency_os_worker'" in source
    assert "REVOKE ALL ON public.learning_candidates FROM agency_os_worker" in source


def test_ci_runs_human_rls_tests_with_a_dedicated_least_privilege_app_login():
    root = PATH.parents[2]
    test_roles = (root / "docker/postgres/test-init.sql").read_text()
    workflow = (root / ".github/workflows/ci.yml").read_text()

    # The test login inherits only the app role's grants; it remains a distinct
    # NOBYPASSRLS login so verify_postgres_role checks the actual session role.
    assert "GRANT agency_os_app TO agency_os_test_app WITH INHERIT TRUE" in test_roles
    assert "ALTER ROLE agency_os_test_app INHERIT" in test_roles
    assert "NOBYPASSRLS" in test_roles

    assert "AGENCY_OS_TEST_RLS_DATABASE_URL:" in workflow
    assert "agency_os_test_app:local-only-test-app-password" in workflow
    assert "AGENCY_OS_TEST_MIGRATOR_DATABASE_URL:" in workflow


def test_agent_session_credential_migration_is_execution_bound_and_private():
    source = (PATH.parent / "r4b8d2f6a103_mcp_session_credentials.py").read_text().lower()

    assert "machine_session_credentials" in source
    assert "enable row level security" in source
    assert "force row level security" in source
    assert "worker_has_execution_context" in source
    assert "worker_mcp_credential_insert" in source
    assert "authenticate_mcp_session_credential" in source
    assert "is_mcp_session_credential_active" in source
    assert "load_mcp_provider_credential" in source
    assert "attach_mcp_provider_credential" in source
    assert "revoke_mcp_session_credential" in source
    assert "mark_mcp_provider_credential_archived" in source
    assert "revoke all on public.machine_session_credentials" in source
    assert "agency_os_app" in source
    assert "agency_os_worker" in source



def test_mcp_session_credential_migration_is_execution_bound_and_hash_only():
    source = (PATH.parent / "r4b8d2f6a103_mcp_session_credentials.py").read_text()
    assert "FORCE ROW LEVEL SECURITY" in source
    assert "worker_mcp_credential_insert" in source
    assert "worker_has_execution_context" in source
    assert "e.machine_session_id" in source
    assert "e.agent_id" in source
    assert "REVOKE ALL ON public.machine_session_credentials" in source
    assert "GRANT INSERT ON public.machine_session_credentials TO agency_os_worker" in source
    assert "SECURITY DEFINER" in source
    assert "authenticate_mcp_session_credential" in source
    assert "is_mcp_session_credential_active" in source
    assert "GRANT EXECUTE" in source
    assert "agency_os_migrator" in source


def test_mcp_session_credentials_are_in_the_runtime_rls_inventory():
    from app.db import REQUIRED_RLS_TABLES
    assert "machine_session_credentials" in REQUIRED_RLS_TABLES


def test_mcp_vault_capacity_migration_is_bounded_and_fails_closed_on_ambiguous_create():
    source = (PATH.parent / "a8c4e6f2b913_mcp_vault_capacity.py").read_text()

    assert "reserve_mcp_vault_credential_slot" in source
    assert "pg_advisory_xact_lock(hashtextextended(p_vault_id, 0))" in source
    assert "least(coalesce(p_max_active_credentials, 16), 20)" in source
    assert "'not_created', 'active', 'delete_pending'" in source
    assert "TO agency_os_worker" in source
    assert "FROM PUBLIC, agency_os_app" in source
    assert "'MCP_VAULT_CREATE_AMBIGUOUS', 'MCP_ORPHANED_CREDENTIAL'" in source
