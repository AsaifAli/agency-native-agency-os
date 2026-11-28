"""Merge workforce integrity and artifact metadata migration heads.

Both branches contain additive schema/security changes. This no-op merge
preserves their history and restores one linear Alembic upgrade target.
"""
from typing import Sequence, Union

revision: str = "g8b4d2f6a1c3"
down_revision: Union[str, Sequence[str], None] = (
    "d1e7a9c3f5b2",
    "f0a1b2c3d4e5",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
