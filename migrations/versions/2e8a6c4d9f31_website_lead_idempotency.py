"""Add idempotency key for website-originated CRM leads.

Revision ID: 2e8a6c4d9f31
Revises: c7a4b1e9d2f6
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "2e8a6c4d9f31"
down_revision: Union[str, Sequence[str], None] = "c7a4b1e9d2f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("external_key", sa.String(160), nullable=True))
    op.create_unique_constraint(
        "uq_lead_external_source_key",
        "leads",
        ["org_id", "workspace_id", "source", "external_key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_lead_external_source_key", "leads", type_="unique")
    op.drop_column("leads", "external_key")
