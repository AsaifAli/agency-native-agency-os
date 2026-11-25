"""Add source-backed lead research and founder-reviewed outreach drafts.

Revision ID: i9b5d7f3a216
Revises: h8a4c6e2f913
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "i9b5d7f3a216"
down_revision: Union[str, Sequence[str], None] = "h8a4c6e2f913"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lead_research_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lead_id", sa.String(36), sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("fit_score", sa.Integer(), nullable=False),
        sa.Column("confidence_score", sa.Integer(), nullable=False),
        sa.Column("buying_signals", sa.JSON(), nullable=False),
        sa.Column("risks", sa.JSON(), nullable=False),
        sa.Column("source_references", sa.JSON(), nullable=False),
        sa.Column("researched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("fit_score BETWEEN 0 AND 100", name="ck_lead_research_fit_score"),
        sa.CheckConstraint("confidence_score BETWEEN 0 AND 100", name="ck_lead_research_confidence_score"),
    )
    op.create_index("ix_lead_research_scope_lead_time", "lead_research_records", ["org_id", "workspace_id", "lead_id", "researched_at"])
    op.create_index("ix_lead_research_records_org_id", "lead_research_records", ["org_id"])
    op.create_index("ix_lead_research_records_workspace_id", "lead_research_records", ["workspace_id"])
    op.create_index("ix_lead_research_records_lead_id", "lead_research_records", ["lead_id"])

    op.create_table(
        "outreach_drafts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lead_id", sa.String(36), sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contact_id", sa.String(36), sa.ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("channel", sa.String(24), nullable=False),
        sa.Column("subject", sa.String(240), nullable=False, server_default=""),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("personalization_basis", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_research_ids", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("reviewed_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("channel IN ('email','linkedin','call_script')", name="ck_outreach_draft_channel"),
        sa.CheckConstraint("status IN ('draft','approved_draft','rejected')", name="ck_outreach_draft_status"),
    )
    op.create_index("ix_outreach_drafts_scope_status", "outreach_drafts", ["org_id", "workspace_id", "status"])
    op.create_index("ix_outreach_drafts_org_id", "outreach_drafts", ["org_id"])
    op.create_index("ix_outreach_drafts_workspace_id", "outreach_drafts", ["workspace_id"])
    op.create_index("ix_outreach_drafts_lead_id", "outreach_drafts", ["lead_id"])
    op.create_index("ix_outreach_drafts_contact_id", "outreach_drafts", ["contact_id"])


def downgrade() -> None:
    op.drop_index("ix_outreach_drafts_contact_id", table_name="outreach_drafts")
    op.drop_index("ix_outreach_drafts_lead_id", table_name="outreach_drafts")
    op.drop_index("ix_outreach_drafts_workspace_id", table_name="outreach_drafts")
    op.drop_index("ix_outreach_drafts_org_id", table_name="outreach_drafts")
    op.drop_index("ix_outreach_drafts_scope_status", table_name="outreach_drafts")
    op.drop_table("outreach_drafts")
    op.drop_index("ix_lead_research_records_lead_id", table_name="lead_research_records")
    op.drop_index("ix_lead_research_records_workspace_id", table_name="lead_research_records")
    op.drop_index("ix_lead_research_records_org_id", table_name="lead_research_records")
    op.drop_index("ix_lead_research_scope_lead_time", table_name="lead_research_records")
    op.drop_table("lead_research_records")
