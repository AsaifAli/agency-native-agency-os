"""Persist revocable browser authentication sessions."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "s9b5d7f1a204"
down_revision: Union[str, Sequence[str], None] = "r8a2c4e6f901"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "browser_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_browser_session_token_hash"),
    )
    op.create_index("ix_browser_session_user_revoked", "browser_sessions", ["user_id", "revoked_at"])
    op.create_index("ix_browser_session_expiry", "browser_sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_browser_session_expiry", table_name="browser_sessions")
    op.drop_index("ix_browser_session_user_revoked", table_name="browser_sessions")
    op.drop_table("browser_sessions")
