from pathlib import Path

import app.db as db
from app.worker import runner

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations" / "versions"


def test_worker_runtime_no_longer_enumerates_global_workspace_scopes():
    assert not hasattr(db, "list_worker_scopes")
    assert not hasattr(db, "scoped_worker_session_factory")
    source = (ROOT / "app" / "worker" / "runner.py").read_text()
    assert "claim_worker_maintenance_scope" in source
    assert "list_worker_scopes" not in source
    assert "scoped_worker_workspace_session_factory" in source


def test_execution_claim_is_atomic_and_only_callable_by_worker_role():
    source = (MIGRATIONS / "c8d2e4f6a1b3_worker_atomic_claim_capability.py").read_text()
    assert "SECURITY DEFINER" in source
    assert "FOR UPDATE SKIP LOCKED" in source
    assert "worker_lease_capabilities" in source
    assert "p_token_hash" in source
    assert "INSERT INTO public.audit_events" in source
    assert "FROM PUBLIC, agency_os_app" in source
    assert "TO agency_os_worker" in source
    assert "session_user <> 'agency_os_worker'" in source


def test_maintenance_claim_is_one_workspace_at_a_time_and_audited():
    source = (MIGRATIONS / "e1f4a6b8c0d2_worker_workspace_maintenance_capabilities.py").read_text()
    assert "claim_worker_maintenance_scope" in source
    assert "FOR UPDATE OF w SKIP LOCKED" in source
    assert "worker_workspace_capabilities" in source
    assert "establish_worker_workspace_context" in source
    assert "worker_has_workspace_context" in source
    assert "release_worker_maintenance_scope" in source
    assert "worker.maintenance_scope_claimed" in source
    assert "TO agency_os_app, agency_os_worker" in source
    compose = (ROOT / "docker-compose.postgres-test.yml").read_text()
    assert "worker_has_workspace_context(text, text) TO agency_os_test_app" in compose
    assert "CREATE POLICY workspace_select" in source
    assert "CREATE POLICY workspace_update" not in source
    assert "CREATE POLICY workspace_delete" not in source
    assert "worker_has_execution_context" in source
    assert "renew_worker_maintenance_scope" in source
    assert "invalidate_worker_execution_capability" in source
    assert "machine_identities.subject_id" in source
    assert "GRANT SELECT ON TABLE public.machine_identities TO agency_os_worker" in source
    assert "REVOKE ALL ON TABLE public.machine_identities FROM agency_os_worker" in source
    assert "GRANT UPDATE (last_used_at) ON TABLE public.machine_identities TO agency_os_worker" in source
    assert "'retry_wait', 'succeeded', 'failed', 'cancelled', 'paused'" in source


def test_maintenance_rls_inventory_matches_the_human_workspace_grant_inventory():
    import importlib.util

    def load(name):
        spec = importlib.util.spec_from_file_location(name, MIGRATIONS / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    human = load("b1c3d5e7f9a2_restore_workspace_grants_after_worker_cutover")
    maintenance = load("e1f4a6b8c0d2_worker_workspace_maintenance_capabilities")
    assert set(maintenance.WORKSPACE_TABLES) == set(human.WORKSPACE_TABLES)


def test_execution_capability_renewal_is_database_verified():
    source = (MIGRATIONS / "d9e3f5a7b2c4_worker_capability_renewal.py").read_text()
    assert "SECURITY DEFINER" in source
    assert "worker_transaction_context" in source
    assert "lease_expires_at" in source
    assert "cap.expires_at > clock_timestamp()" in source
    assert "TO agency_os_worker" in source


def test_runner_does_not_skip_maintenance_or_execution_polling():
    assert callable(runner.run_worker)
    source = (ROOT / "app" / "worker" / "runner.py").read_text()
    assert "_run_maintenance(" in source
    assert "_run_session_maintenance(" in source
    assert "_run_outbox_maintenance(" in source
    assert "MaintenanceLeaseHeartbeat" in source
    assert "lease_heartbeat.assert_healthy()" in source
    assert "processor(" in source


def test_worker_claim_rpc_casts_varchar_ids_to_declared_text_types():
    source = (
        MIGRATIONS / "f2a6c8e0b4d1_worker_claim_return_type_fix.py"
    ).read_text()
    assert "target.id::text" in source
    assert "target.org_id::text" in source
    assert "target.workspace_id::text" in source
    assert "RETURNS TABLE(" in source


def test_postgres_test_image_includes_compose_file_for_contract_tests():
    dockerfile = (ROOT / "Dockerfile.postgres-test").read_text()
    assert "COPY docker-compose.postgres-test.yml ." in dockerfile
