"""Merge the current worker/security and application migration heads.

This no-op revision gives new application schema changes one linear parent
without rewriting previously released migration history.
"""
from typing import Sequence, Union

revision: str = "aa1b2c3d4e5f"
down_revision: Union[str, Sequence[str], None] = (
    "m4c8e2a6f913",
    "z6f1b3d8a2c5",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
