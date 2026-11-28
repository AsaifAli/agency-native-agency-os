"""Merge workforce integrity and artifact metadata migration heads.

This no-op revision joins the independently developed tenant-integrity and
artifact-metadata migration paths. It preserves both histories and restores a
single linear Alembic head for fresh installs and upgrades.
"""
from typing import Sequence, Union

revision: str = "b9c3d7e1f5a2"
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
