
"""add single use approval consumption

Revision ID: eb75d47bfc63
Revises: d47c880cb7fd
Create Date: 2026-11-11 19:34:19.690049
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "eb75d47bfc63"
down_revision: Union[str, Sequence[str], None] = "d47c880cb7fd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "approvals",
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "approvals",
        sa.Column("consumed_by", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_approvals_consumed_by_users",
        "approvals",
        "users",
        ["consumed_by"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_approvals_consumed_by_users",
        "approvals",
        type_="foreignkey",
    )
    op.drop_column("approvals", "consumed_by")
    op.drop_column("approvals", "consumed_at")
