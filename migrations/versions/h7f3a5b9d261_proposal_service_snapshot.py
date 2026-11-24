"""Snapshot service catalogue revision on proposal drafts.

Revision ID: h7f3a5b9d261
Revises: g6e2f4a8c195
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "h7f3a5b9d261"
down_revision: Union[str, Sequence[str], None] = "g6e2f4a8c195"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("proposals", sa.Column("service_offering_id", sa.String(36), nullable=True))
    op.add_column("proposals", sa.Column("service_offering_snapshot", sa.JSON(), nullable=True))
    op.create_foreign_key(
        "fk_proposals_service_offering_id_service_offerings", "proposals", "service_offerings",
        ["service_offering_id"], ["id"], ondelete="RESTRICT",
    )
    op.create_index("ix_proposals_service_offering_id", "proposals", ["service_offering_id"])


def downgrade() -> None:
    op.drop_index("ix_proposals_service_offering_id", table_name="proposals")
    op.drop_constraint("fk_proposals_service_offering_id_service_offerings", "proposals", type_="foreignkey")
    op.drop_column("proposals", "service_offering_snapshot")
    op.drop_column("proposals", "service_offering_id")
