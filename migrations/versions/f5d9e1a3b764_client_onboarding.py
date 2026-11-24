"""Create contract-backed client onboarding and delivery handoff.

Revision ID: f5d9e1a3b764
Revises: e4c8d0f2a653
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "f5d9e1a3b764"
down_revision: Union[str, Sequence[str], None] = "e4c8d0f2a653"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_onboardings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", sa.String(36), sa.ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("contract_id", sa.String(36), sa.ForeignKey("contract_records.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="preparing"),
        sa.Column("approval_id", sa.String(36), sa.ForeignKey("approvals.id"), nullable=True),
        sa.Column("activation_plan", sa.JSON(), nullable=False),
        sa.Column("project_name", sa.String(240), nullable=False, server_default=""),
        sa.Column("budget_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_hours", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "workspace_id", "contract_id", name="uq_onboarding_contract"),
        sa.CheckConstraint("status IN ('preparing','pending_approval','active','paused','completed','cancelled')", name="ck_client_onboarding_status"),
        sa.CheckConstraint("budget_minor >= 0 AND estimated_hours >= 0", name="ck_onboarding_project_plan_nonnegative"),
    )
    op.create_index("ix_client_onboardings_scope_status", "client_onboardings", ["org_id", "workspace_id", "status"])
    op.create_index("ix_client_onboardings_org_id", "client_onboardings", ["org_id"])
    op.create_index("ix_client_onboardings_workspace_id", "client_onboardings", ["workspace_id"])
    op.create_index("ix_client_onboardings_client_id", "client_onboardings", ["client_id"])
    op.create_index("ix_client_onboardings_contract_id", "client_onboardings", ["contract_id"])
    op.create_index("ix_client_onboardings_project_id", "client_onboardings", ["project_id"])

    op.create_table(
        "onboarding_checklist_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("onboarding_id", sa.String(36), sa.ForeignKey("client_onboardings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("completion_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("completed_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("waived_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("waived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "workspace_id", "onboarding_id", "code", name="uq_onboarding_item_code"),
        sa.CheckConstraint("status IN ('open','completed','waived')", name="ck_onboarding_item_status"),
    )
    op.create_index("ix_onboarding_items_scope_status", "onboarding_checklist_items", ["org_id", "workspace_id", "onboarding_id", "status"])
    op.create_index("ix_onboarding_checklist_items_org_id", "onboarding_checklist_items", ["org_id"])
    op.create_index("ix_onboarding_checklist_items_workspace_id", "onboarding_checklist_items", ["workspace_id"])
    op.create_index("ix_onboarding_checklist_items_onboarding_id", "onboarding_checklist_items", ["onboarding_id"])


def downgrade() -> None:
    op.drop_index("ix_onboarding_checklist_items_onboarding_id", table_name="onboarding_checklist_items")
    op.drop_index("ix_onboarding_checklist_items_workspace_id", table_name="onboarding_checklist_items")
    op.drop_index("ix_onboarding_checklist_items_org_id", table_name="onboarding_checklist_items")
    op.drop_index("ix_onboarding_items_scope_status", table_name="onboarding_checklist_items")
    op.drop_table("onboarding_checklist_items")
    op.drop_index("ix_client_onboardings_project_id", table_name="client_onboardings")
    op.drop_index("ix_client_onboardings_contract_id", table_name="client_onboardings")
    op.drop_index("ix_client_onboardings_client_id", table_name="client_onboardings")
    op.drop_index("ix_client_onboardings_workspace_id", table_name="client_onboardings")
    op.drop_index("ix_client_onboardings_org_id", table_name="client_onboardings")
    op.drop_index("ix_client_onboardings_scope_status", table_name="client_onboardings")
    op.drop_table("client_onboardings")
