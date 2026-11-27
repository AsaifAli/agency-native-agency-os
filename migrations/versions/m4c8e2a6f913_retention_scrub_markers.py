"""Add non-destructive retention markers for session and tool payload scrubbing.

Revision ID: m4c8e2a6f913
Revises: l2e8a0b6d549
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "m4c8e2a6f913"
down_revision: Union[str, Sequence[str], None] = "l2e8a0b6d549"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_sessions",
        sa.Column("metadata_purged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tool_invocations",
        sa.Column("payload_purged_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tool_invocations", "payload_purged_at")
    op.drop_column("agent_sessions", "metadata_purged_at")
