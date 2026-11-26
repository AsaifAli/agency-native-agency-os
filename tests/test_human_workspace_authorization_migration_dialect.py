import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "migrations/versions/v2c4e6a8b0d2_human_workspace_authorization.py"
)
SPEC = importlib.util.spec_from_file_location(
    "human_workspace_authorization_migration", MIGRATION_PATH
)
MIGRATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MIGRATION)


def _run(engine: sa.Engine, operation: str) -> None:
    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        original_op = MIGRATION.op
        try:
            MIGRATION.op = operations
            getattr(MIGRATION, operation)()
        finally:
            MIGRATION.op = original_op


def _database() -> sa.Engine:
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    organizations = sa.Table(
        "organizations", metadata, sa.Column("id", sa.String(36), primary_key=True)
    )
    users = sa.Table(
        "users",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("active", sa.Boolean, nullable=False),
    )
    workspaces = sa.Table(
        "workspaces",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.UniqueConstraint("org_id", "id", name="uq_workspaces_org_id"),
    )
    memberships = sa.Table(
        "memberships",
        metadata,
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id")),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id")),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(organizations.insert(), [{"id": "org-1"}])
        connection.execute(
            users.insert(),
            [{"id": "active-user", "active": True}, {"id": "inactive-user", "active": False}],
        )
        connection.execute(workspaces.insert(), [{"id": "ws-1", "org_id": "org-1"}])
        connection.execute(
            memberships.insert(),
            [
                {"org_id": "org-1", "user_id": "active-user"},
                {"org_id": "org-1", "user_id": "inactive-user"},
            ],
        )
    return engine


def test_workspace_authorization_migration_creates_and_backfills_grants_on_sqlite():
    engine = _database()

    _run(engine, "upgrade")

    inspector = sa.inspect(engine)
    assert "workspace_grants" in inspector.get_table_names()
    assert "created_by" in {column["name"] for column in inspector.get_columns("workspaces")}
    assert len(inspector.get_foreign_keys("workspaces")) == 2

    with engine.connect() as connection:
        grants = connection.execute(
            sa.text(
                "SELECT org_id, workspace_id, user_id, granted_by "
                "FROM workspace_grants"
            )
        ).mappings().all()

    assert grants == [
        {
            "org_id": "org-1",
            "workspace_id": "ws-1",
            "user_id": "active-user",
            "granted_by": "active-user",
        }
    ]


def test_workspace_authorization_migration_downgrade_removes_only_added_sqlite_schema():
    engine = _database()
    _run(engine, "upgrade")

    _run(engine, "downgrade")

    inspector = sa.inspect(engine)
    assert "workspace_grants" not in inspector.get_table_names()
    assert "created_by" not in {
        column["name"] for column in inspector.get_columns("workspaces")
    }
    assert len(inspector.get_foreign_keys("workspaces")) == 1
