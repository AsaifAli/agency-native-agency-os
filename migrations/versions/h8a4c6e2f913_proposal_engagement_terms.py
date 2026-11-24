"""Add explicit one-time and retainer engagement terms to proposals.

Revision ID: h8a4c6e2f913
Revises: g6e2f4a8c195
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "h8a4c6e2f913"
down_revision: Union[str, Sequence[str], None] = "g6e2f4a8c195"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("proposals", sa.Column("engagement_type", sa.String(24), nullable=False, server_default="one_time"))
    op.add_column("proposals", sa.Column("billing_frequency", sa.String(24), nullable=False, server_default="one_time"))
    op.add_column("proposals", sa.Column("term_months", sa.Integer(), nullable=True))
    op.add_column("proposals", sa.Column("included_hours_per_period", sa.Integer(), nullable=True))
    op.add_column("proposals", sa.Column("rollover_hours", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("proposals", sa.Column("support_response_hours", sa.Integer(), nullable=True))
    op.add_column("proposals", sa.Column("auto_renew", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_check_constraint("ck_proposal_engagement_type", "proposals", "engagement_type IN ('one_time','retainer')")
    op.create_check_constraint("ck_proposal_billing_frequency", "proposals", "billing_frequency IN ('one_time','monthly','quarterly','annual')")
    op.create_check_constraint(
        "ck_proposal_engagement_terms", "proposals",
        "(engagement_type = 'one_time' AND billing_frequency = 'one_time' AND term_months IS NULL AND included_hours_per_period IS NULL AND rollover_hours = false AND auto_renew = false) OR (engagement_type = 'retainer' AND billing_frequency IN ('monthly','quarterly','annual') AND term_months BETWEEN 1 AND 60 AND included_hours_per_period IS NOT NULL AND included_hours_per_period >= 0)",
    )
    op.create_check_constraint("ck_proposal_support_response_hours", "proposals", "support_response_hours IS NULL OR support_response_hours BETWEEN 1 AND 720")


def downgrade() -> None:
    op.drop_constraint("ck_proposal_support_response_hours", "proposals", type_="check")
    op.drop_constraint("ck_proposal_engagement_terms", "proposals", type_="check")
    op.drop_constraint("ck_proposal_billing_frequency", "proposals", type_="check")
    op.drop_constraint("ck_proposal_engagement_type", "proposals", type_="check")
    for name in ("auto_renew", "support_response_hours", "rollover_hours", "included_hours_per_period", "term_months", "billing_frequency", "engagement_type"):
        op.drop_column("proposals", name)
