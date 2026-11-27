import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "migrations/versions/e3f1a9c7b2d4_outbox_delivery_reliability.py"
)
SPEC = importlib.util.spec_from_file_location(
    "outbox_delivery_migration", MIGRATION_PATH
)
MIGRATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MIGRATION)


def _run_upgrade(engine: sa.Engine) -> None:
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        operations = Operations(context)
        original_op = MIGRATION.op
        try:
            MIGRATION.op = operations
            MIGRATION.upgrade()
        finally:
            MIGRATION.op = original_op


def test_outbox_reliability_migration_adds_check_constraint_and_index_on_sqlite():
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                CREATE TABLE outbox_events (
                    id VARCHAR(36) PRIMARY KEY,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    status VARCHAR(32) NOT NULL,
                    available_at DATETIME NOT NULL
                )
                """
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO outbox_events "
                "(id, attempts, status, available_at) "
                "VALUES ('evt-1', 0, 'pending', CURRENT_TIMESTAMP)"
            )
        )

    _run_upgrade(engine)

    inspector = sa.inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("outbox_events")}
    assert {
        "max_attempts",
        "claimed_by",
        "lease_expires_at",
        "published_at",
        "last_error",
    } <= columns

    checks = inspector.get_check_constraints("outbox_events")
    assert any(
        check["name"] == "ck_outbox_attempts"
        and "attempts >= 0" in check["sqltext"]
        and "max_attempts >= 1" in check["sqltext"]
        for check in checks
    )

    indexes = {index["name"]: index for index in inspector.get_indexes("outbox_events")}
    assert indexes["ix_outbox_lease_recovery"]["column_names"] == [
        "status",
        "lease_expires_at",
        "available_at",
    ]

    with engine.connect() as connection:
        row = connection.execute(
            sa.text("SELECT id, attempts, max_attempts FROM outbox_events")
        ).one()
        assert tuple(row) == ("evt-1", 0, 8)

    # A retry after successful DDL must be idempotent.
    _run_upgrade(engine)
