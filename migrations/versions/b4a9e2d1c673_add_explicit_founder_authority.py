"""Add explicit founder authority separate from organization roles.

Revision ID: b4a9e2d1c673
Revises: 7a2d9c4e1f60
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "b4a9e2d1c673"
down_revision: Union[str, Sequence[str], None] = "7a2d9c4e1f60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "founder_authorities",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "org_id", sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("grant_source", sa.String(length=40), nullable=False, server_default="cli_provisioning"),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("org_id", "user_id", name="uq_founder_authority_org_user"),
    )
    op.create_index("ix_founder_authorities_org_id", "founder_authorities", ["org_id"])
    op.create_index("ix_founder_authorities_user_id", "founder_authorities", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_founder_authorities_user_id", table_name="founder_authorities")
    op.drop_index("ix_founder_authorities_org_id", table_name="founder_authorities")
    op.drop_table("founder_authorities")
