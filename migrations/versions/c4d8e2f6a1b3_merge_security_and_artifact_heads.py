"""Join the completed workforce/security and artifact migration lines.

The preceding no-op revisions preserve independently authored migration
histories. This final merge provides one unambiguous upgrade target.
"""
from typing import Sequence, Union

revision: str = "c4d8e2f6a1b3"
down_revision: Union[str, Sequence[str], None] = (
    "b9c3d7e1f5a2",
    "e2f8a1c6d3b5",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
