"""Persist asynchronously generated Chief of Staff plan drafts.

Revision ID: a7c2d59e481b
Revises: 4d9e7a1c6b30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7c2d59e481b"
down_revision: Union[str, Sequence[str], None] = "4d9e7a1c6b30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orchestration_plan_drafts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("execution_id", sa.String(length=36), nullable=False),
        sa.Column("requested_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("created_by_member_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("plan_title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="queued", nullable=False),
        sa.Column("suggested_plan", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("approved_plan_id", sa.String(length=36), nullable=True),
        sa.Column("reviewed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued','running','ready_for_review','invalid_output','failed','approved','rejected','cancelled')",
            name="ck_orchestration_plan_draft_status",
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["execution_id"], ["executions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_member_id"], ["workforce_members.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approved_plan_id"], ["orchestration_plans.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("execution_id", name="uq_orchestration_plan_draft_execution"),
        sa.UniqueConstraint(
            "org_id", "workspace_id", "idempotency_key",
            name="uq_orchestration_plan_draft_idempotency",
        ),
    )
    op.create_index(
        "ix_orchestration_plan_draft_scope_status",
        "orchestration_plan_drafts",
        ["org_id", "workspace_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_orchestration_plan_draft_scope_status",
        table_name="orchestration_plan_drafts",
    )
    op.drop_table("orchestration_plan_drafts")
