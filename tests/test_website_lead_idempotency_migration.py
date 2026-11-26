import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "migrations/versions/2e8a6c4d9f31_website_lead_idempotency.py"
)
SPEC = importlib.util.spec_from_file_location(
    "website_lead_idempotency_migration", MIGRATION_PATH
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


def _create_leads_table(engine: sa.Engine, *, external_key: bool = False) -> None:
    with engine.begin() as connection:
        external_key_column = (
            ", external_key VARCHAR(160)" if external_key else ""
        )
        connection.execute(
            sa.text(
                """
                CREATE TABLE leads (
                    id VARCHAR(36) PRIMARY KEY,
                    org_id VARCHAR(36) NOT NULL,
                    workspace_id VARCHAR(36) NOT NULL,
                    source VARCHAR(80) NOT NULL
                    {external_key_column}
                )
                """.format(external_key_column=external_key_column)
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO leads (id, org_id, workspace_id, source) "
                "VALUES ('lead-1', 'org-1', 'ws-1', 'website')"
            )
        )


def test_website_lead_idempotency_migration_adds_unique_constraint_on_sqlite():
    engine = sa.create_engine("sqlite://")
    _create_leads_table(engine)

    _run_upgrade(engine)

    inspector = sa.inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("leads")}
    assert "external_key" in columns
    constraints = inspector.get_unique_constraints("leads")
    assert any(
        item["name"] == "uq_lead_external_source_key"
        and item["column_names"] == [
            "org_id", "workspace_id", "source", "external_key"
        ]
        for item in constraints
    )

    with engine.connect() as connection:
        row = connection.execute(
            sa.text("SELECT id, external_key FROM leads")
        ).one()
        assert tuple(row) == ("lead-1", None)


def test_website_lead_idempotency_migration_recovers_after_partial_sqlite_ddl():
    engine = sa.create_engine("sqlite://")
    _create_leads_table(engine, external_key=True)

    _run_upgrade(engine)
    _run_upgrade(engine)

    inspector = sa.inspect(engine)
    columns = [column["name"] for column in inspector.get_columns("leads")]
    assert columns.count("external_key") == 1
    constraints = inspector.get_unique_constraints("leads")
    matching = [
        item for item in constraints
        if item["name"] == "uq_lead_external_source_key"
    ]
    assert len(matching) == 1
    assert matching[0]["column_names"] == [
        "org_id", "workspace_id", "source", "external_key"
    ]
