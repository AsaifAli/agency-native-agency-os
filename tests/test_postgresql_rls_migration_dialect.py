import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "migrations/versions/t0a1b2c3d4e5_postgresql_tenant_row_level_security.py"
)
SPEC = importlib.util.spec_from_file_location("postgresql_rls_migration", MIGRATION_PATH)
MIGRATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MIGRATION)


def _run(engine: sa.Engine, operation: str) -> None:
    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        original_op = MIGRATION.op
        try:
            MIGRATION.op = operations
            getattr(MIGRATION, operation)()
        finally:
            MIGRATION.op = original_op


def test_postgresql_rls_migration_is_noop_on_sqlite_upgrade_and_downgrade():
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE organizations (id TEXT PRIMARY KEY)"))
        connection.execute(sa.text("CREATE TABLE browser_sessions (id TEXT PRIMARY KEY)"))

    _run(engine, "upgrade")
    _run(engine, "downgrade")

    inspector = sa.inspect(engine)
    assert inspector.get_table_names() == ["browser_sessions", "organizations"]
    assert inspector.get_schema_names() == ["main"]
