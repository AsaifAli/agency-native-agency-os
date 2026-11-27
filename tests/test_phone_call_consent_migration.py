import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "migrations/versions/f9c2a6d8e410_phone_call_consent_evidence.py"
)
SPEC = importlib.util.spec_from_file_location(
    "phone_call_consent_evidence_migration", MIGRATION_PATH
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
            sa.text("CREATE TABLE contacts (id VARCHAR(36) PRIMARY KEY)")
        )
        if partial:
            connection.execute(
                sa.text(
                    "ALTER TABLE contacts ADD COLUMN "
                    "phone_call_consent_status VARCHAR(24) NOT NULL DEFAULT 'unknown'"
                )
            )


def _assert_phone_consent_schema(engine: sa.Engine) -> None:
    inspector = sa.inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("contacts")}
    assert {
        "phone_call_consent_status",
        "phone_call_consent_source",
        "phone_call_consent_recorded_at",
    } <= columns
    checks = {
        item["name"]: item["sqltext"]
        for item in inspector.get_check_constraints("contacts")
    }
    assert "ck_contact_phone_call_consent_status" in checks
    assert "ck_contact_phone_call_consent_evidence" in checks
    assert "granted" in checks["ck_contact_phone_call_consent_status"]
    assert "phone_call_consent_recorded_at" in checks[
        "ck_contact_phone_call_consent_evidence"
    ]


def test_phone_call_consent_migration_is_sqlite_safe_and_idempotent():
    engine = sa.create_engine("sqlite://")
    _base_schema(engine)

    _run_upgrade(engine)
    _run_upgrade(engine)

    _assert_phone_consent_schema(engine)


def test_phone_call_consent_migration_recovers_from_partial_sqlite_ddl():
    engine = sa.create_engine("sqlite://")
    _base_schema(engine, partial=True)

    _run_upgrade(engine)

    _assert_phone_consent_schema(engine)
