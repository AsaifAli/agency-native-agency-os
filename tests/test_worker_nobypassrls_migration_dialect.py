import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "migrations/versions/u1b2c3d4e5f6_worker_nobypassrls_scope.py"
)
SPEC = importlib.util.spec_from_file_location("worker_nobypassrls_migration", MIGRATION_PATH)
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


def test_worker_nobypassrls_migration_is_noop_on_sqlite_upgrade_and_downgrade():
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE organizations (id TEXT PRIMARY KEY)"))

    _run(engine, "upgrade")
    _run(engine, "downgrade")

    assert sa.inspect(engine).get_table_names() == ["organizations"]
