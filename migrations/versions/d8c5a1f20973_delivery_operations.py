"""Add service playbooks, scope changes, time entries and project costs.

Revision ID: d8c5a1f20973
Revises: b4a9e2d1c673
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "d8c5a1f20973"
down_revision: Union[str, Sequence[str], None] = "b4a9e2d1c673"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("contract_value_minor", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("projects", sa.Column("estimated_hours", sa.Integer(), nullable=False, server_default="0"))

    op.create_table(
        "service_playbooks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("service_line", sa.String(80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("workflow", sa.JSON(), nullable=False),
        sa.Column("required_inputs", sa.JSON(), nullable=False),
        sa.Column("deliverables", sa.JSON(), nullable=False),
        sa.Column("acceptance_criteria", sa.JSON(), nullable=False),
        sa.Column("security_checks", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('draft','active','retired')", name="ck_playbook_status"),
    )
    op.create_index("ix_service_playbooks_org_id", "service_playbooks", ["org_id"])
    op.create_index("ix_service_playbooks_workspace_id", "service_playbooks", ["workspace_id"])
    op.create_index("ix_playbooks_scope_status", "service_playbooks", ["org_id", "workspace_id", "status"])

    op.create_table(
        "scope_change_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("impact_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("estimated_hours_delta", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("budget_delta_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("contract_value_delta_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("schedule_days_delta", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending_approval"),
        sa.Column("requested_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("decided_by", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("approval_id", sa.String(36), sa.ForeignKey("approvals.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('pending_approval','approved','rejected')", name="ck_scope_change_status"),
    )
    op.create_index("ix_scope_change_requests_org_id", "scope_change_requests", ["org_id"])
    op.create_index("ix_scope_change_requests_workspace_id", "scope_change_requests", ["workspace_id"])
    op.create_index("ix_scope_change_requests_project_id", "scope_change_requests", ["project_id"])
    op.create_index("ix_scope_changes_project_status", "scope_change_requests", ["org_id", "workspace_id", "project_id", "status"])

    op.create_table(
        "time_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id")),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("billable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("hourly_cost_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("duration_minutes > 0 AND duration_minutes <= 1440", name="ck_time_entry_duration"),
        sa.CheckConstraint("hourly_cost_minor >= 0", name="ck_time_entry_cost_rate"),
    )
    op.create_index("ix_time_entries_org_id", "time_entries", ["org_id"])
    op.create_index("ix_time_entries_workspace_id", "time_entries", ["workspace_id"])
    op.create_index("ix_time_entries_project_id", "time_entries", ["project_id"])
    op.create_index("ix_time_entries_project_date", "time_entries", ["org_id", "workspace_id", "project_id", "started_at"])

    op.create_table(
        "project_costs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("incurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_minor >= 0", name="ck_project_cost_nonnegative"),
    )
    op.create_index("ix_project_costs_org_id", "project_costs", ["org_id"])
    op.create_index("ix_project_costs_workspace_id", "project_costs", ["workspace_id"])
    op.create_index("ix_project_costs_project_id", "project_costs", ["project_id"])
    op.create_index("ix_project_costs_project_date", "project_costs", ["org_id", "workspace_id", "project_id", "incurred_at"])


def downgrade() -> None:
    op.drop_table("project_costs")
    op.drop_table("time_entries")
    op.drop_table("scope_change_requests")
    op.drop_table("service_playbooks")
    op.drop_column("projects", "estimated_hours")
    op.drop_column("projects", "contract_value_minor")
