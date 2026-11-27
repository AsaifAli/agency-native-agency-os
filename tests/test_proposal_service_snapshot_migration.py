import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "migrations/versions/h7f3a5b9d261_proposal_service_snapshot.py"
)
SPEC = importlib.util.spec_from_file_location(
    "proposal_service_snapshot_migration", MIGRATION_PATH
)
MIGRATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MIGRATION)


def _run_upgrade(engine: sa.Engine) -> None:
    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        original_op = MIGRATION.op
        try:
            MIGRATION.op = operations
            MIGRATION.upgrade()
        finally:
            MIGRATION.op = original_op


def _base_schema(engine: sa.Engine, *, partial: bool = False) -> None:
    with engine.begin() as connection:
        connection.execute(
            sa.text("CREATE TABLE service_offerings (id VARCHAR(36) PRIMARY KEY)")
        )
        connection.execute(
            sa.text("CREATE TABLE proposals (id VARCHAR(36) PRIMARY KEY)")
        )
        if partial:
            connection.execute(
                sa.text(
                    "ALTER TABLE proposals ADD COLUMN service_offering_id VARCHAR(36)"
                )
            )


def _assert_schema(engine: sa.Engine) -> None:
    inspector = sa.inspect(engine)
    columns = {item["name"] for item in inspector.get_columns("proposals")}
    assert {"service_offering_id", "service_offering_snapshot"} <= columns

    indexes = {item["name"] for item in inspector.get_indexes("proposals")}
    assert "ix_proposals_service_offering_id" in indexes

    foreign_keys = inspector.get_foreign_keys("proposals")
    assert any(
        item.get("name") == "fk_proposals_service_offering_id_service_offerings"
        and item.get("constrained_columns") == ["service_offering_id"]
        and item.get("referred_table") == "service_offerings"
        for item in foreign_keys
    )


def test_proposal_service_snapshot_migration_is_sqlite_safe_and_idempotent():
    engine = sa.create_engine("sqlite://")
    _base_schema(engine)

    _run_upgrade(engine)
    _run_upgrade(engine)

    _assert_schema(engine)


def test_proposal_service_snapshot_migration_recovers_when_column_exists():
    engine = sa.create_engine("sqlite://")
    _base_schema(engine, partial=True)

    _run_upgrade(engine)

    _assert_schema(engine)
