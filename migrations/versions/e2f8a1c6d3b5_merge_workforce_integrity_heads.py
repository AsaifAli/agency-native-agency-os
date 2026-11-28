"""Merge application security and workforce-integrity migration lines.

Revision ID: e2f8a1c6d3b5
Revises: aa1b2c3d4e5f, d1e7a9c3f5b2
"""
from typing import Sequence, Union

revision: str = "e2f8a1c6d3b5"
down_revision: Union[str, Sequence[str], None] = (
    "aa1b2c3d4e5f",
    "d1e7a9c3f5b2",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
