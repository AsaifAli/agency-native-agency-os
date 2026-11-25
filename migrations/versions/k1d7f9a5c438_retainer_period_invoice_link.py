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
    with op.batch_alter_table("invoice_records") as batch_op:
        batch_op.add_column(
            sa.Column(
                "retainer_period_id", sa.String(36),
                sa.ForeignKey("retainer_service_periods.id", ondelete="RESTRICT"),
                nullable=True,
            ),
        )
        batch_op.create_index(
            "ix_invoice_records_retainer_period_id", ["retainer_period_id"],
        )
        batch_op.create_unique_constraint(
            "uq_invoice_retainer_period",
            ["org_id", "workspace_id", "retainer_period_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("invoice_records") as batch_op:
        batch_op.drop_constraint("uq_invoice_retainer_period", type_="unique")
        batch_op.drop_index("ix_invoice_records_retainer_period_id")
        batch_op.drop_column("retainer_period_id")
