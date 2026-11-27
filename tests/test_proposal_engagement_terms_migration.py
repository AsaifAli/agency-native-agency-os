import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "migrations/versions/h8a4c6e2f913_proposal_engagement_terms.py"
)
SPEC = importlib.util.spec_from_file_location(
    "proposal_engagement_terms_migration", MIGRATION_PATH
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
            sa.text("CREATE TABLE proposals (id VARCHAR(36) PRIMARY KEY)")
        )
        if partial:
            connection.execute(
                sa.text(
                    "ALTER TABLE proposals ADD COLUMN engagement_type "
                    "VARCHAR(24) NOT NULL DEFAULT 'one_time'"
                )
            )
            connection.execute(
                sa.text(
                    "ALTER TABLE proposals ADD COLUMN billing_frequency "
                    "VARCHAR(24) NOT NULL DEFAULT 'one_time'"
                )
            )
            connection.execute(
                sa.text(
                    "ALTER TABLE proposals ADD COLUMN term_months INTEGER"
                )
            )
            connection.execute(
                sa.text(
                    "ALTER TABLE proposals ADD COLUMN included_hours_per_period INTEGER"
                )
            )
            connection.execute(
                sa.text(
                    "ALTER TABLE proposals ADD COLUMN rollover_hours "
                    "BOOLEAN NOT NULL DEFAULT 0"
                )
            )
            connection.execute(
                sa.text(
                    "ALTER TABLE proposals ADD COLUMN support_response_hours INTEGER"
                )
            )
            connection.execute(
                sa.text(
                    "ALTER TABLE proposals ADD COLUMN auto_renew "
                    "BOOLEAN NOT NULL DEFAULT 0"
                )
            )


def _assert_schema(engine: sa.Engine) -> None:
    inspector = sa.inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("proposals")}
    expected_columns = {
        "engagement_type",
        "billing_frequency",
        "term_months",
        "included_hours_per_period",
        "rollover_hours",
        "support_response_hours",
        "auto_renew",
    }
    assert expected_columns <= columns

    checks = {
        item["name"]: item.get("sqltext", "")
        for item in inspector.get_check_constraints("proposals")
    }
    expected_checks = {
        "ck_proposal_engagement_type",
        "ck_proposal_billing_frequency",
        "ck_proposal_engagement_terms",
        "ck_proposal_support_response_hours",
    }
    assert expected_checks <= checks.keys()
    assert "retainer" in checks["ck_proposal_engagement_type"]
    assert "quarterly" in checks["ck_proposal_billing_frequency"]
    assert "term_months" in checks["ck_proposal_engagement_terms"]
    assert "support_response_hours" in checks[
        "ck_proposal_support_response_hours"
    ]


def test_proposal_engagement_terms_migration_is_sqlite_safe_and_idempotent():
    engine = sa.create_engine("sqlite://")
    _base_schema(engine)

    _run_upgrade(engine)
    _run_upgrade(engine)

    _assert_schema(engine)


def test_proposal_engagement_terms_migration_recovers_after_partial_ddl():
    engine = sa.create_engine("sqlite://")
    _base_schema(engine, partial=True)

    _run_upgrade(engine)

    _assert_schema(engine)
