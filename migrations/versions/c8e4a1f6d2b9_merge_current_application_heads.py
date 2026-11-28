"""Converge workforce integrity and artifact metadata migration heads."""
from typing import Sequence, Union

revision: str = "c8e4a1f6d2b9"
down_revision: Union[str, Sequence[str], None] = (
    "e2f8a1c6d3b5",
    "b9c3d7e1f5a2",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
