"""Merge outbound, proposal snapshot and engagement feature revisions.

Revision ID: l2e8a0b6d549
Revises: h7f3a5c9d2e6, h7f3a5b9d261, k1d7f9a5c438
"""
from typing import Sequence, Union

revision: str = "l2e8a0b6d549"
down_revision: Union[str, Sequence[str], None] = (
    "h7f3a5c9d2e6",
    "h7f3a5b9d261",
    "k1d7f9a5c438",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
