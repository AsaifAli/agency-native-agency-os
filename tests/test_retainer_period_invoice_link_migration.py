import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "migrations/versions/k1d7f9a5c438_retainer_period_invoice_link.py"
)
SPEC = importlib.util.spec_from_file_location(
    "retainer_period_invoice_link_migration", MIGRATION_PATH
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
        connection.execute(sa.text("CREATE TABLE retainer_service_periods (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(sa.text("CREATE TABLE invoice_records (id VARCHAR(36) PRIMARY KEY, org_id VARCHAR(36) NOT NULL, workspace_id VARCHAR(36) NOT NULL)"))
        if partial:
            connection.execute(
                sa.text(
                    "ALTER TABLE invoice_records ADD COLUMN retainer_period_id VARCHAR(36)"
                )
            )


def _assert_schema(engine: sa.Engine) -> None:
    inspector = sa.inspect(engine)
    columns = {item["name"] for item in inspector.get_columns("invoice_records")}
    assert "retainer_period_id" in columns

    indexes = {item["name"] for item in inspector.get_indexes("invoice_records")}
    assert "ix_invoice_records_retainer_period_id" in indexes

    unique_constraints = {
        item["name"]: item.get("column_names", [])
        for item in inspector.get_unique_constraints("invoice_records")
    }
    assert unique_constraints.get("uq_invoice_retainer_period") == [
        "org_id", "workspace_id", "retainer_period_id"
    ]

    foreign_keys = inspector.get_foreign_keys("invoice_records")
    assert any(
        item.get("name") == "fk_invoice_records_retainer_period_id_retainer_service_periods"
        and item.get("constrained_columns") == ["retainer_period_id"]
        and item.get("referred_table") == "retainer_service_periods"
        for item in foreign_keys
    )


def test_retainer_invoice_link_migration_is_sqlite_safe_and_idempotent():
    engine = sa.create_engine("sqlite://")
    _base_schema(engine)

    _run_upgrade(engine)
    _run_upgrade(engine)

    _assert_schema(engine)


def test_retainer_invoice_link_migration_recovers_when_column_already_exists():
    engine = sa.create_engine("sqlite://")
    _base_schema(engine, partial=True)

    _run_upgrade(engine)

    _assert_schema(engine)
