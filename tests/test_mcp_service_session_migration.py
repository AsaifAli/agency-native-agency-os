import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


PATH = Path(__file__).parents[1] / "migrations/versions/b7d4c9a2e6f1_service_mcp_sessions.py"
SPEC = importlib.util.spec_from_file_location("service_mcp_sessions_migration", PATH)
MIGRATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MIGRATION)


def test_service_mcp_session_migration_is_noop_on_sqlite_upgrade_and_downgrade():
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        original = MIGRATION.op
        try:
            MIGRATION.op = operations
            MIGRATION.upgrade()
            MIGRATION.downgrade()
        finally:
            MIGRATION.op = original
    assert sa.inspect(engine).get_table_names() == []


def test_service_mcp_definers_bind_to_the_authenticated_machine_identity():
    source_path = Path(__file__).parents[1] / "migrations/versions/c3d4e5f6a7b8_bind_service_mcp_credentials.py"
    source = source_path.read_text()
    assert source.count("current_setting('agency_os.machine_identity_lookup_id', true)") >= 2
    assert source.count("IS DISTINCT FROM p_machine_identity_id") >= 2
    assert source.count("current_setting('agency_os.machine_org_id', true)") >= 2
    assert source.count("current_setting('agency_os.machine_workspace_id', true)") >= 2


def test_service_mcp_identity_binding_migration_is_noop_on_sqlite():
    path = Path(__file__).parents[1] / "migrations/versions/c3d4e5f6a7b8_bind_service_mcp_credentials.py"
    spec = importlib.util.spec_from_file_location("service_mcp_identity_binding_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        original = migration.op
        try:
            migration.op = operations
            migration.upgrade()
            migration.downgrade()
        finally:
            migration.op = original
    assert sa.inspect(engine).get_table_names() == []
