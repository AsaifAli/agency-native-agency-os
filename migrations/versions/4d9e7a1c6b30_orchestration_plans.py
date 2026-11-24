"""Merge existing heads and add Chief of Staff orchestration records.

Revision ID: 4d9e7a1c6b30
Revises: d8c5a1f20973, c7a4b1e9d2f6, 2e8a6c4d9f31
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "4d9e7a1c6b30"
down_revision: Union[str, Sequence[str], None] = (
    "d8c5a1f20973",
    "c7a4b1e9d2f6",
    "2e8a6c4d9f31",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orchestration_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("root_task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_member_id", sa.String(36), sa.ForeignKey("workforce_members.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("plan_title", sa.String(200), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="planned"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('planned','in_progress','awaiting_review','succeeded','failed','cancelled')", name="ck_orchestration_plan_status"),
    )
    op.create_index("ix_orchestration_plan_scope_status", "orchestration_plans", ["org_id", "workspace_id", "status"])
    op.create_index("ix_orchestration_plan_root_task", "orchestration_plans", ["root_task_id"])

    op.add_column("delegations", sa.Column("status", sa.String(24), nullable=False, server_default="ready"))
    op.add_column("delegations", sa.Column("sequence_no", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("delegations", sa.Column("last_error_code", sa.String(80), nullable=True))
    op.add_column("delegations", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_check_constraint(
        "ck_delegation_status", "delegations",
        "status IN ('blocked','ready','queued','running','awaiting_review','succeeded','failed','cancelled')",
    )
    op.create_index("ix_delegation_scope_status", "delegations", ["org_id", "workspace_id", "status"])

    op.create_table(
        "orchestration_plan_delegations",
        sa.Column("plan_id", sa.String(36), sa.ForeignKey("orchestration_plans.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("delegation_id", sa.String(36), sa.ForeignKey("delegations.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.UniqueConstraint("plan_id", "ordinal", name="uq_plan_delegation_ordinal"),
    )


def downgrade() -> None:
    op.drop_table("orchestration_plan_delegations")
    op.drop_index("ix_delegation_scope_status", table_name="delegations")
    op.drop_constraint("ck_delegation_status", "delegations", type_="check")
    op.drop_column("delegations", "updated_at")
    op.drop_column("delegations", "last_error_code")
    op.drop_column("delegations", "sequence_no")
    op.drop_column("delegations", "status")
    op.drop_index("ix_orchestration_plan_root_task", table_name="orchestration_plans")
    op.drop_index("ix_orchestration_plan_scope_status", table_name="orchestration_plans")
    op.drop_table("orchestration_plans")
