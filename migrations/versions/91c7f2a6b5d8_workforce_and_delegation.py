"""Add governed AI workforce and task delegation records.

Revision ID: 91c7f2a6b5d8
Revises: e3f1a9c7b2d4
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "91c7f2a6b5d8"
down_revision: Union[str, Sequence[str], None] = "e3f1a9c7b2d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workforce_units",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_unit_id", sa.String(36), sa.ForeignKey("workforce_units.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("unit_type", sa.String(24), nullable=False),
        sa.Column("department_key", sa.String(80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("unit_type IN ('office','group','department','team')", name="ck_workforce_unit_type"),
        sa.UniqueConstraint("org_id", "workspace_id", "department_key", "name", name="uq_workforce_unit_name"),
    )
    op.create_index("ix_workforce_unit_scope_parent", "workforce_units", ["org_id", "workspace_id", "parent_unit_id"])

    op.create_table(
        "workforce_members",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("unit_id", sa.String(36), sa.ForeignKey("workforce_units.id", ondelete="CASCADE"), nullable=True),
        sa.Column("manager_member_id", sa.String(36), sa.ForeignKey("workforce_members.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("agent_id", sa.String(36), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("member_type", sa.String(24), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("department_key", sa.String(80), nullable=False),
        sa.Column("responsibilities", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("autonomy_level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(24), nullable=False, server_default="planned"),
        sa.Column("is_founder_reserved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("member_type IN ('human','agent','supervisor','sub_agent')", name="ck_workforce_member_type"),
        sa.CheckConstraint("autonomy_level BETWEEN 0 AND 3", name="ck_workforce_autonomy_level"),
        sa.CheckConstraint("status IN ('planned','active','paused','retired')", name="ck_workforce_member_status"),
        sa.UniqueConstraint("org_id", "workspace_id", "name", "title", name="uq_workforce_member_name_title"),
    )
    op.create_index("ix_workforce_member_scope_manager", "workforce_members", ["org_id", "workspace_id", "manager_member_id"])
    op.create_index("ix_workforce_member_scope_unit", "workforce_members", ["org_id", "workspace_id", "unit_id"])

    op.create_table(
        "workforce_capabilities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("member_id", sa.String(36), sa.ForeignKey("workforce_members.id", ondelete="CASCADE"), nullable=False),
        sa.Column("capability_key", sa.String(120), nullable=False),
        sa.Column("scope", sa.String(24), nullable=False, server_default="workspace"),
        sa.Column("allowed_data_classes", sa.JSON(), nullable=False, server_default='["synthetic"]'),
        sa.Column("allowed_actions", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("tool_allowlist", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("budget_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("scope IN ('self','team','workspace')", name="ck_workforce_capability_scope"),
        sa.CheckConstraint("budget_minor >= 0", name="ck_workforce_capability_budget"),
        sa.UniqueConstraint("member_id", "capability_key", name="uq_workforce_member_capability"),
    )
    op.create_index("ix_workforce_capability_scope", "workforce_capabilities", ["org_id", "workspace_id", "member_id"])

    op.create_table(
        "delegations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("child_task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("delegated_by_member_id", sa.String(36), sa.ForeignKey("workforce_members.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("assigned_to_member_id", sa.String(36), sa.ForeignKey("workforce_members.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("dependency_task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("review_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("review_status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("parent_task_id <> child_task_id", name="ck_delegation_non_self"),
        sa.CheckConstraint("review_status IN ('pending','approved','changes_requested','waived')", name="ck_delegation_review_status"),
        sa.UniqueConstraint("parent_task_id", "child_task_id", name="uq_delegation_parent_child"),
    )
    op.create_index("ix_delegation_scope_parent", "delegations", ["org_id", "workspace_id", "parent_task_id"])
    op.create_index("ix_delegation_scope_assignee", "delegations", ["org_id", "workspace_id", "assigned_to_member_id"])


def downgrade() -> None:
    op.drop_index("ix_delegation_scope_assignee", table_name="delegations")
    op.drop_index("ix_delegation_scope_parent", table_name="delegations")
    op.drop_table("delegations")
    op.drop_index("ix_workforce_capability_scope", table_name="workforce_capabilities")
    op.drop_table("workforce_capabilities")
    op.drop_index("ix_workforce_member_scope_unit", table_name="workforce_members")
    op.drop_index("ix_workforce_member_scope_manager", table_name="workforce_members")
    op.drop_table("workforce_members")
    op.drop_index("ix_workforce_unit_scope_parent", table_name="workforce_units")
    op.drop_table("workforce_units")
