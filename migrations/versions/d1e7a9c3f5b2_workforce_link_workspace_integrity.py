"""Enforce organization/workspace integrity for workforce relationships.

Revision ID: d1e7a9c3f5b2
Revises: aa1b2c3d4e5f
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d1e7a9c3f5b2"
down_revision: Union[str, Sequence[str], None] = "aa1b2c3d4e5f"
branch_labels = None
depends_on = None


UNIQUE_INDEXES = (
    ("agents", "uq_agent_scope_id", ["org_id", "workspace_id", "id"]),
    ("tasks", "uq_task_scope_id", ["org_id", "workspace_id", "id"]),
    ("workforce_units", "uq_workforce_unit_scope_id", ["org_id", "workspace_id", "id"]),
    ("workforce_members", "uq_workforce_member_scope_id", ["org_id", "workspace_id", "id"]),
)

SCOPED_FOREIGN_KEYS = {
    "workforce_members": (
        ("fk_workforce_member_unit_workspace", ["org_id", "workspace_id", "unit_id"],
         "workforce_units", ["org_id", "workspace_id", "id"]),
        ("fk_workforce_member_manager_workspace", ["org_id", "workspace_id", "manager_member_id"],
         "workforce_members", ["org_id", "workspace_id", "id"]),
        ("fk_workforce_member_agent_workspace", ["org_id", "workspace_id", "agent_id"],
         "agents", ["org_id", "workspace_id", "id"]),
    ),
    "workforce_capabilities": (
        ("fk_workforce_capability_member_workspace", ["org_id", "workspace_id", "member_id"],
         "workforce_members", ["org_id", "workspace_id", "id"]),
    ),
    "delegations": (
        ("fk_delegation_parent_task_workspace", ["org_id", "workspace_id", "parent_task_id"],
         "tasks", ["org_id", "workspace_id", "id"]),
        ("fk_delegation_child_task_workspace", ["org_id", "workspace_id", "child_task_id"],
         "tasks", ["org_id", "workspace_id", "id"]),
        ("fk_delegation_dependency_task_workspace", ["org_id", "workspace_id", "dependency_task_id"],
         "tasks", ["org_id", "workspace_id", "id"]),
        ("fk_delegation_delegated_by_workspace", ["org_id", "workspace_id", "delegated_by_member_id"],
         "workforce_members", ["org_id", "workspace_id", "id"]),
        ("fk_delegation_assignee_workspace", ["org_id", "workspace_id", "assigned_to_member_id"],
         "workforce_members", ["org_id", "workspace_id", "id"]),
    ),
}


def _ensure_index(bind: sa.Connection, table: str, name: str, columns: list[str]) -> None:
    indexes = {item["name"]: item for item in sa.inspect(bind).get_indexes(table)}
    if name in indexes:
        existing = indexes[name]
        if existing.get("column_names") != columns or not existing.get("unique"):
            raise RuntimeError(f"Unexpected definition for {name}")
        return
    op.create_index(name, table, columns, unique=True)


def _validate_relationship(
    bind: sa.Connection,
    *,
    source_table: str,
    source_column: str,
    target_table: str,
    label: str,
) -> None:
    invalid = bind.execute(sa.text(f"""
        SELECT count(*)
        FROM {source_table} AS source
        LEFT JOIN {target_table} AS target
          ON target.id = source.{source_column}
         AND target.org_id = source.org_id
         AND target.workspace_id = source.workspace_id
        WHERE source.{source_column} IS NOT NULL
          AND target.id IS NULL
    """)).scalar_one()
    if invalid:
        raise RuntimeError(
            f"Cannot enforce workforce workspace integrity: {label} contains "
            f"{invalid} orphaned or cross-workspace reference(s)"
        )


def _validate_existing_relationships(bind: sa.Connection) -> None:
    required = {
        "agents", "tasks", "workforce_units", "workforce_members",
        "workforce_capabilities", "delegations",
    }
    inspector = sa.inspect(bind)
    missing = sorted(table for table in required if not inspector.has_table(table))
    if missing:
        raise RuntimeError(
            "Cannot enforce workforce workspace integrity; missing tables: "
            + ", ".join(missing)
        )

    checks = (
        ("workforce_members", "unit_id", "workforce_units", "member unit"),
        ("workforce_members", "manager_member_id", "workforce_members", "member manager"),
        ("workforce_members", "agent_id", "agents", "member agent"),
        ("workforce_capabilities", "member_id", "workforce_members", "capability member"),
        ("delegations", "parent_task_id", "tasks", "delegation parent task"),
        ("delegations", "child_task_id", "tasks", "delegation child task"),
        ("delegations", "dependency_task_id", "tasks", "delegation dependency task"),
        ("delegations", "delegated_by_member_id", "workforce_members", "delegation creator"),
        ("delegations", "assigned_to_member_id", "workforce_members", "delegation assignee"),
    )
    for source, column, target, label in checks:
        _validate_relationship(
            bind, source_table=source, source_column=column,
            target_table=target, label=label,
        )


def _install_foreign_keys(bind: sa.Connection, table: str, definitions: tuple) -> None:
    existing = {
        item.get("name")
        for item in sa.inspect(bind).get_foreign_keys(table)
    }
    missing = [item for item in definitions if item[0] not in existing]
    if not missing:
        return

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(table) as batch:
            for name, local_columns, target_table, remote_columns in missing:
                batch.create_foreign_key(
                    name, target_table, local_columns, remote_columns,
                    ondelete="RESTRICT",
                )
    else:
        for name, local_columns, target_table, remote_columns in missing:
            op.create_foreign_key(
                name, table, target_table, local_columns, remote_columns,
                ondelete="RESTRICT",
            )


def upgrade() -> None:
    bind = op.get_bind()
    _validate_existing_relationships(bind)

    for table, name, columns in UNIQUE_INDEXES:
        _ensure_index(bind, table, name, columns)

    for table, definitions in SCOPED_FOREIGN_KEYS.items():
        _install_foreign_keys(bind, table, definitions)


def downgrade() -> None:
    raise RuntimeError(
        "Unsafe downgrade refused: removing workforce workspace constraints "
        "would weaken tenant isolation"
    )
