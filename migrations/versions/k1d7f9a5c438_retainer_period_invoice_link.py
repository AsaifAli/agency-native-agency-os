"""Link retainer service periods to recurring invoice drafts.

Revision ID: k1d7f9a5c438
Revises: j0c6e8f4b327
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "k1d7f9a5c438"
down_revision: Union[str, Sequence[str], None] = "j0c6e8f4b327"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "invoice_records",
        sa.Column(
            "retainer_period_id", sa.String(36),
            sa.ForeignKey("retainer_service_periods.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_invoice_records_retainer_period_id",
        "invoice_records", ["retainer_period_id"],
    )
    op.create_unique_constraint(
        "uq_invoice_retainer_period",
        "invoice_records",
        ["org_id", "workspace_id", "retainer_period_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_invoice_retainer_period", "invoice_records", type_="unique")
    op.drop_index("ix_invoice_records_retainer_period_id", table_name="invoice_records")
    op.drop_column("invoice_records", "retainer_period_id")
