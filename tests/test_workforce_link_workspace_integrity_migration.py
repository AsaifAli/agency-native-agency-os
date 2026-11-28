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
    / "migrations/versions/d1e7a9c3f5b2_workforce_link_workspace_integrity.py"
)
SPEC = importlib.util.spec_from_file_location(
    "workforce_link_workspace_integrity_migration", MIGRATION_PATH
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


def _base_schema(engine, *, cross_workspace_member=False):
    with engine.begin() as connection:
        for table in ("agents", "tasks", "workforce_units"):
            connection.execute(sa.text(
                f"CREATE TABLE {table} (id VARCHAR(36) PRIMARY KEY, "
                "org_id VARCHAR(36) NOT NULL, workspace_id VARCHAR(36) NOT NULL)"
            ))
        connection.execute(sa.text("""
            CREATE TABLE workforce_members (
                id VARCHAR(36) PRIMARY KEY, org_id VARCHAR(36) NOT NULL,
                workspace_id VARCHAR(36) NOT NULL, unit_id VARCHAR(36),
                manager_member_id VARCHAR(36), agent_id VARCHAR(36)
            )
        """))
        connection.execute(sa.text("""
            CREATE TABLE workforce_capabilities (
                id VARCHAR(36) PRIMARY KEY, org_id VARCHAR(36) NOT NULL,
                workspace_id VARCHAR(36) NOT NULL, member_id VARCHAR(36) NOT NULL
            )
        """))
        connection.execute(sa.text("""
            CREATE TABLE delegations (
                id VARCHAR(36) PRIMARY KEY, org_id VARCHAR(36) NOT NULL,
                workspace_id VARCHAR(36) NOT NULL, parent_task_id VARCHAR(36) NOT NULL,
                child_task_id VARCHAR(36) NOT NULL, dependency_task_id VARCHAR(36),
                delegated_by_member_id VARCHAR(36) NOT NULL,
                assigned_to_member_id VARCHAR(36) NOT NULL
            )
        """))
        for table in ("agents", "tasks", "workforce_units"):
            connection.execute(sa.text(
                f"INSERT INTO {table} (id, org_id, workspace_id) VALUES "
                "(:id_a, 'org-a', 'workspace-a'), "
                "(:id_b, 'org-a', 'workspace-b')"
            ), {"id_a": f"{table}-a", "id_b": f"{table}-b"})
        connection.execute(sa.text(
            "INSERT INTO workforce_members "
            "(id, org_id, workspace_id, unit_id, manager_member_id, agent_id) "
            "VALUES ('member-a', 'org-a', 'workspace-a', 'workforce_units-a', NULL, 'agents-a'), "
            "('member-b', 'org-a', 'workspace-b', 'workforce_units-b', NULL, 'agents-b')"
        ))
        if cross_workspace_member:
            connection.execute(sa.text(
                "INSERT INTO workforce_members "
                "(id, org_id, workspace_id, agent_id) "
                "VALUES ('member-invalid', 'org-a', 'workspace-a', 'agents-b')"
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


def test_workforce_links_are_workspace_scoped_at_database_boundary():
    engine = _engine()
    _base_schema(engine)

    _run_upgrade(engine)
    _run_upgrade(engine)

    with engine.begin() as connection:
        connection.execute(sa.text(
            "INSERT INTO workforce_capabilities (id, org_id, workspace_id, member_id) "
            "VALUES ('cap-a', 'org-a', 'workspace-a', 'member-a')"
        ))
        connection.execute(sa.text(
            "INSERT INTO delegations (id, org_id, workspace_id, parent_task_id, "
            "child_task_id, delegated_by_member_id, assigned_to_member_id) "
            "VALUES ('delegation-a', 'org-a', 'workspace-a', 'tasks-a', 'tasks-b', "
            "'member-a', 'member-a')"
        ))

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(sa.text(
                "INSERT INTO workforce_members (id, org_id, workspace_id, agent_id) "
                "VALUES ('member-cross-agent', 'org-a', 'workspace-a', 'agents-b')"
            ))

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(sa.text(
                "INSERT INTO workforce_capabilities (id, org_id, workspace_id, member_id) "
                "VALUES ('cap-cross-member', 'org-a', 'workspace-a', 'member-b')"
            ))

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(sa.text(
                "INSERT INTO delegations (id, org_id, workspace_id, parent_task_id, "
                "child_task_id, delegated_by_member_id, assigned_to_member_id) "
                "VALUES ('delegation-cross-task', 'org-a', 'workspace-a', 'tasks-a', "
                "'tasks-b', 'member-a', 'member-b')"
            ))


def test_workforce_link_migration_fails_closed_on_existing_cross_workspace_rows():
    engine = _engine()
    _base_schema(engine, cross_workspace_member=True)

    with pytest.raises(RuntimeError, match="cross-workspace"):
        _run_upgrade(engine)
