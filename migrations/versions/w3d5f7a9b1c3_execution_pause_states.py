"""Persist execution and attempt pause states.

PostgreSQL enum values are additive. Downgrade intentionally leaves the values
in place because removing enum labels safely requires rebuilding dependent
columns and can break rows written after this migration.
"""
from alembic import op

revision = "w3d5f7a9b1c3"
down_revision = "v2c4e6a8b0d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        # SQLite stores SQLAlchemy Enum values as VARCHAR; create_all already
        # includes the new labels for isolated unit tests.
        return
    op.execute("ALTER TYPE executionstatus ADD VALUE IF NOT EXISTS 'paused'")
    op.execute("ALTER TYPE executionattemptstatus ADD VALUE IF NOT EXISTS 'paused'")


def downgrade() -> None:
    # PostgreSQL enum labels are intentionally retained; see module docstring.
    pass
