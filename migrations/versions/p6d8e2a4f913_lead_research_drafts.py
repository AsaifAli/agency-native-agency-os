"""Add source-backed lead research drafts with founder review.

Revision ID: p6d8e2a4f913
Revises: o5c3d9e1f742
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "p6d8e2a4f913"
down_revision: Union[str, Sequence[str], None] = "o5c3d9e1f742"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lead_research_drafts",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("machine_identity_id", sa.String(36), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("company_name", sa.String(200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("source_references", sa.JSON(), nullable=False),
        sa.Column("fit_score", sa.Integer(), nullable=False),
        sa.Column("confidence_score", sa.Integer(), nullable=False),
        sa.Column("buying_signals", sa.JSON(), nullable=False),
        sa.Column("risks", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending_review"),
        sa.Column("review_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("promoted_lead_id", sa.String(36), nullable=True),
        sa.Column("reviewed_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "workspace_id", "id", name="uq_lead_research_drafts_scope_id"),
        sa.UniqueConstraint("org_id", "workspace_id", "idempotency_key", name="uq_lead_research_draft_idempotency"),
        sa.ForeignKeyConstraint(["org_id", "workspace_id"], ["workspaces.org_id", "workspaces.id"], ondelete="CASCADE", name="fk_lead_research_drafts_workspace_scope"),
        sa.ForeignKeyConstraint(["org_id", "workspace_id", "machine_identity_id"], ["machine_identities.org_id", "machine_identities.workspace_id", "machine_identities.id"], ondelete="RESTRICT", name="fk_lead_research_drafts_machine_identity_scope"),
        sa.ForeignKeyConstraint(["org_id", "workspace_id", "promoted_lead_id"], ["leads.org_id", "leads.workspace_id", "leads.id"], ondelete="RESTRICT", name="fk_lead_research_drafts_promoted_lead_scope"),
        sa.CheckConstraint("fit_score BETWEEN 0 AND 100", name="ck_lead_research_draft_fit_score"),
        sa.CheckConstraint("confidence_score BETWEEN 0 AND 100", name="ck_lead_research_draft_confidence_score"),
        sa.CheckConstraint("status IN ('pending_review','approved','rejected','promoted')", name="ck_lead_research_draft_status"),
    )
    op.create_index("ix_lead_research_drafts_scope_status_created", "lead_research_drafts", ["org_id", "workspace_id", "status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_lead_research_drafts_scope_status_created", table_name="lead_research_drafts")
    op.drop_table("lead_research_drafts")
