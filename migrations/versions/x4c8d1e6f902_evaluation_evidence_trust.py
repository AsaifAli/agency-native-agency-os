"""Mark self-submitted evaluation evidence as unverified.

No API path currently issues trusted runner attestations, so evaluation runs
created through the ordinary API remain ineligible for release gating.
"""
from alembic import op
import sqlalchemy as sa

revision = "x4c8d1e6f902"
down_revision = "w3d5f7a9b1c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "evaluation_runs",
        sa.Column("evidence_trust", sa.String(length=32), nullable=False,
                  server_default="self_reported"),
    )


def downgrade() -> None:
    op.drop_column("evaluation_runs", "evidence_trust")
