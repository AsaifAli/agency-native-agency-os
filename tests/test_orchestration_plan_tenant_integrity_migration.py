import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError


MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "migrations/versions/c4d6e8f0a2b5_orchestration_plan_link_scope.py"
)
SPEC = importlib.util.spec_from_file_location(
    "orchestration_plan_link_scope_migration", MIGRATION_PATH
)
MIGRATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MIGRATION)


def _engine():
    engine = sa.create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def _base_schema(engine, *, cross_workspace_link=False):
    with engine.begin() as connection:
        connection.execute(sa.text(
            "CREATE TABLE organizations (id VARCHAR(36) PRIMARY KEY)"
        ))
        connection.execute(sa.text(
            "CREATE TABLE workspaces (id VARCHAR(36) PRIMARY KEY, org_id VARCHAR(36) NOT NULL)"
        ))
        connection.execute(sa.text(
            "CREATE TABLE tasks (id VARCHAR(36) PRIMARY KEY)"
        ))
        connection.execute(sa.text(
            "CREATE TABLE workforce_members (id VARCHAR(36) PRIMARY KEY)"
        ))
        connection.execute(sa.text(
            "CREATE TABLE delegations (id VARCHAR(36) PRIMARY KEY, org_id VARCHAR(36) NOT NULL, workspace_id VARCHAR(36) NOT NULL)"
        ))
        connection.execute(sa.text(
            "CREATE TABLE orchestration_plans (id VARCHAR(36) PRIMARY KEY, org_id VARCHAR(36) NOT NULL, workspace_id VARCHAR(36) NOT NULL)"
        ))
        connection.execute(sa.text(
            """
            CREATE TABLE orchestration_plan_delegations (
                plan_id VARCHAR(36) NOT NULL,
                delegation_id VARCHAR(36) NOT NULL,
                ordinal INTEGER NOT NULL,
                PRIMARY KEY (plan_id, delegation_id),
                CONSTRAINT uq_plan_delegation_ordinal UNIQUE (plan_id, ordinal)
            )
            """
        ))
        connection.execute(sa.text(
            "INSERT INTO organizations (id) VALUES ('org-a')"
        ))
        connection.execute(sa.text(
            "INSERT INTO workspaces (id, org_id) VALUES ('workspace-a', 'org-a'), ('workspace-b', 'org-a')"
        ))
        connection.execute(sa.text(
            "INSERT INTO delegations (id, org_id, workspace_id) VALUES "
            "('delegation-a', 'org-a', 'workspace-a'), "
            "('delegation-b', 'org-a', 'workspace-b')"
        ))
        connection.execute(sa.text(
            "INSERT INTO orchestration_plans (id, org_id, workspace_id) VALUES "
            "('plan-a', 'org-a', 'workspace-a'), "
            "('plan-b', 'org-a', 'workspace-b')"
        ))
        if cross_workspace_link:
            connection.execute(sa.text(
                "INSERT INTO orchestration_plan_delegations (plan_id, delegation_id, ordinal) "
                "VALUES ('plan-a', 'delegation-b', 1)"
            ))
        else:
            connection.execute(sa.text(
                "INSERT INTO orchestration_plan_delegations (plan_id, delegation_id, ordinal) "
                "VALUES ('plan-a', 'delegation-a', 1), ('plan-b', 'delegation-b', 1)"
            ))


def _run_upgrade(engine):
    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        original_op = MIGRATION.op
        try:
            MIGRATION.op = operations
            MIGRATION.upgrade()
        finally:
            MIGRATION.op = original_op


def test_orchestration_plan_links_are_backfilled_and_reject_cross_workspace_pairs():
    engine = _engine()
    _base_schema(engine)

    _run_upgrade(engine)
    # A partially/repeated migration must not duplicate constraints or indexes.
    _run_upgrade(engine)

    inspector = sa.inspect(engine)
    columns = {column["name"] for column in inspector.get_columns(
        "orchestration_plan_delegations"
    )}
    assert {"org_id", "workspace_id", "plan_id", "delegation_id", "ordinal"} <= columns
    column_map = {
        column["name"]: column for column in inspector.get_columns(
            "orchestration_plan_delegations"
        )
    }
    assert column_map["org_id"]["nullable"] is False
    assert column_map["workspace_id"]["nullable"] is False
    foreign_keys = {
        item["name"] for item in inspector.get_foreign_keys(
            "orchestration_plan_delegations"
        )
    }
    assert foreign_keys == {
        "fk_plan_delegation_plan_workspace",
        "fk_plan_delegation_delegation_workspace",
    }
    indexes = {
        item["name"] for item in inspector.get_indexes(
            "orchestration_plan_delegations"
        )
    }
    assert "ix_orchestration_plan_delegations_scope_delegation" in indexes

    with engine.connect() as connection:
        rows = connection.execute(sa.text(
            "SELECT plan_id, delegation_id, org_id, workspace_id "
            "FROM orchestration_plan_delegations ORDER BY plan_id"
        )).mappings().all()
        assert [(row["plan_id"], row["org_id"], row["workspace_id"]) for row in rows] == [
            ("plan-a", "org-a", "workspace-a"),
            ("plan-b", "org-a", "workspace-b"),
        ]

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(sa.text(
                "INSERT INTO orchestration_plan_delegations "
                "(org_id, workspace_id, plan_id, delegation_id, ordinal) "
                "VALUES ('org-a', 'workspace-a', 'plan-a', 'delegation-b', 2)"
            ))


def test_orchestration_plan_link_migration_fails_closed_on_existing_cross_workspace_data():
    engine = _engine()
    _base_schema(engine, cross_workspace_link=True)

    with pytest.raises(RuntimeError, match="cross-workspace"):
        _run_upgrade(engine)
