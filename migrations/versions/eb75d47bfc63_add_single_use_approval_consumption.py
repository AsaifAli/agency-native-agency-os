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

_CONSUMED_BY_FK = "fk_approvals_consumed_by_users"


def upgrade() -> None:
    # SQLite cannot ALTER TABLE to add a foreign-key constraint. Batch mode
    # performs the required copy-and-move rebuild. Inspect first because SQLite
    # DDL is not transactional: an earlier failed attempt may have added one or
    # both columns while leaving the Alembic revision at its parent.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("approvals")}
    existing_foreign_keys = {
        foreign_key.get("name")
        for foreign_key in inspector.get_foreign_keys("approvals")
    }

    with op.batch_alter_table("approvals") as batch_op:
        if "consumed_at" not in existing_columns:
            batch_op.add_column(
                sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True)
            )
        if "consumed_by" not in existing_columns:
            batch_op.add_column(
                sa.Column("consumed_by", sa.String(length=36), nullable=True)
            )
        if _CONSUMED_BY_FK not in existing_foreign_keys:
            batch_op.create_foreign_key(
                _CONSUMED_BY_FK,
                "users",
                ["consumed_by"],
                ["id"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("approvals")}
    existing_foreign_keys = {
        foreign_key.get("name")
        for foreign_key in inspector.get_foreign_keys("approvals")
    }

    with op.batch_alter_table("approvals") as batch_op:
        if _CONSUMED_BY_FK in existing_foreign_keys:
            batch_op.drop_constraint(_CONSUMED_BY_FK, type_="foreignkey")
        if "consumed_by" in existing_columns:
            batch_op.drop_column("consumed_by")
        if "consumed_at" in existing_columns:
            batch_op.drop_column("consumed_at")
