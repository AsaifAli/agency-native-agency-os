"""Create founder-governed commercial proposal drafts.

Revision ID: c7b1a4e9d630
Revises: b8d4e6f1a203
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "c7b1a4e9d630"
down_revision: Union[str, Sequence[str], None] = "b8d4e6f1a203"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "proposals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("opportunity_id", sa.String(36), sa.ForeignKey("opportunities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("service_line", sa.String(120), nullable=False),
        sa.Column("scope_summary", sa.Text(), nullable=False),
        sa.Column("deliverables", sa.JSON(), nullable=False),
        sa.Column("assumptions", sa.JSON(), nullable=False),
        sa.Column("exclusions", sa.JSON(), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("validity_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("approval_id", sa.String(36), sa.ForeignKey("approvals.id"), nullable=True),
        sa.Column("approved_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('draft','pending_approval','approved','rejected','withdrawn')", name="ck_proposal_status"),
        sa.CheckConstraint("amount_minor >= 0", name="ck_proposal_amount_nonnegative"),
        sa.CheckConstraint("validity_days >= 1 AND validity_days <= 180", name="ck_proposal_validity_days"),
    )
    op.create_index("ix_proposals_scope_status", "proposals", ["org_id", "workspace_id", "status"])
    op.create_index("ix_proposals_org_id", "proposals", ["org_id"])
    op.create_index("ix_proposals_workspace_id", "proposals", ["workspace_id"])
    op.create_index("ix_proposals_opportunity_id", "proposals", ["opportunity_id"])


def downgrade() -> None:
    op.drop_index("ix_proposals_opportunity_id", table_name="proposals")
    op.drop_index("ix_proposals_workspace_id", table_name="proposals")
    op.drop_index("ix_proposals_org_id", table_name="proposals")
    op.drop_index("ix_proposals_scope_status", table_name="proposals")
    op.drop_table("proposals")
