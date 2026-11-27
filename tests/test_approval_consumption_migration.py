import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "migrations/versions/eb75d47bfc63_add_single_use_approval_consumption.py"
)
SPEC = importlib.util.spec_from_file_location(
    "approval_consumption_migration", MIGRATION_PATH
)
MIGRATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MIGRATION)


def _run_upgrade(*, partially_applied: bool) -> sa.Engine:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(sa.text("CREATE TABLE approvals (id VARCHAR(36) PRIMARY KEY)"))
        if partially_applied:
            connection.execute(
                sa.text("ALTER TABLE approvals ADD COLUMN consumed_at DATETIME")
            )
            connection.execute(
                sa.text("ALTER TABLE approvals ADD COLUMN consumed_by VARCHAR(36)")
            )

        context = MigrationContext.configure(connection)
        operations = Operations(context)
        original_op = MIGRATION.op
        try:
            MIGRATION.op = operations
            MIGRATION.upgrade()
        finally:
            MIGRATION.op = original_op
    return engine


def test_approval_consumption_migration_adds_columns_and_foreign_key_on_sqlite():
    engine = _run_upgrade(partially_applied=False)
    inspector = sa.inspect(engine)

    assert {"consumed_at", "consumed_by"} <= {
        column["name"] for column in inspector.get_columns("approvals")
    }
    foreign_keys = inspector.get_foreign_keys("approvals")
    assert any(
        foreign_key["name"] == "fk_approvals_consumed_by_users"
        and foreign_key["referred_table"] == "users"
        and foreign_key["constrained_columns"] == ["consumed_by"]
        for foreign_key in foreign_keys
    )


def test_approval_consumption_migration_recovers_after_partial_sqlite_ddl():
    engine = _run_upgrade(partially_applied=True)
    inspector = sa.inspect(engine)

    columns = [column["name"] for column in inspector.get_columns("approvals")]
    assert columns.count("consumed_at") == 1
    assert columns.count("consumed_by") == 1
    assert any(
        foreign_key["name"] == "fk_approvals_consumed_by_users"
        for foreign_key in inspector.get_foreign_keys("approvals")
    )
