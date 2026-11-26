import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "migrations/versions/4d9e7a1c6b30_orchestration_plans.py"
)
SPEC = importlib.util.spec_from_file_location(
    "orchestration_plans_migration", MIGRATION_PATH
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


def _base_schema(engine: sa.Engine, *, partial: bool = False) -> None:
    with engine.begin() as connection:
        for table in ("organizations", "workspaces", "tasks", "workforce_members"):
            connection.execute(
                sa.text(f"CREATE TABLE {table} (id VARCHAR(36) PRIMARY KEY)")
            )
        connection.execute(
            sa.text(
                """
                CREATE TABLE delegations (
                    id VARCHAR(36) PRIMARY KEY,
                    org_id VARCHAR(36) NOT NULL,
                    workspace_id VARCHAR(36) NOT NULL
                )
                """
            )
        )
        if partial:
            connection.execute(
                sa.text(
                    "ALTER TABLE delegations ADD COLUMN status "
                    "VARCHAR(24) NOT NULL DEFAULT 'ready'"
                )
            )
            connection.execute(
                sa.text(
                    "ALTER TABLE delegations ADD COLUMN sequence_no "
                    "INTEGER NOT NULL DEFAULT 1"
                )
            )


def test_orchestration_migration_adds_check_constraint_and_catalogue_on_sqlite():
    engine = sa.create_engine("sqlite://")
    _base_schema(engine)

    _run_upgrade(engine)

    inspector = sa.inspect(engine)
    assert inspector.has_table("orchestration_plans")
    assert inspector.has_table("orchestration_plan_delegations")
    delegation_columns = {
        column["name"] for column in inspector.get_columns("delegations")
    }
    assert {
        "status", "sequence_no", "last_error_code", "updated_at"
    } <= delegation_columns
    checks = inspector.get_check_constraints("delegations")
    assert any(
        item["name"] == "ck_delegation_status"
        and "awaiting_review" in item["sqltext"]
        for item in checks
    )
    indexes = {
        item["name"] for item in inspector.get_indexes("delegations")
    }
    assert "ix_delegation_scope_status" in indexes


def test_orchestration_migration_recovers_from_partial_sqlite_ddl():
    engine = sa.create_engine("sqlite://")
    _base_schema(engine, partial=True)

    _run_upgrade(engine)

    inspector = sa.inspect(engine)
    assert inspector.has_table("orchestration_plans")
    assert inspector.has_table("orchestration_plan_delegations")
    assert sum(
        column["name"] == "status"
        for column in inspector.get_columns("delegations")
    ) == 1
    assert sum(
        item["name"] == "ck_delegation_status"
        for item in inspector.get_check_constraints("delegations")
    ) == 1
    assert sum(
        item["name"] == "ix_delegation_scope_status"
        for item in inspector.get_indexes("delegations")
    ) == 1
