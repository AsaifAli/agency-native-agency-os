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
