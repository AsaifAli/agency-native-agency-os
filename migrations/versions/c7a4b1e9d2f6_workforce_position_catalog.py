"""Add full agency position and team catalogue.

Revision ID: c7a4b1e9d2f6
Revises: 91c7f2a6b5d8
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "c7a4b1e9d2f6"
down_revision: Union[str, Sequence[str], None] = "91c7f2a6b5d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workforce_positions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("unit_id", sa.String(36), sa.ForeignKey("workforce_units.id", ondelete="CASCADE"), nullable=True),
        sa.Column("team_unit_id", sa.String(36), sa.ForeignKey("workforce_units.id", ondelete="SET NULL"), nullable=True),
        sa.Column("assigned_member_id", sa.String(36), sa.ForeignKey("workforce_members.id", ondelete="SET NULL"), nullable=True),
        sa.Column("position_key", sa.String(160), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("department_key", sa.String(80), nullable=False),
        sa.Column("group_key", sa.String(80), nullable=False),
        sa.Column("team_key", sa.String(100), nullable=False),
        sa.Column("reports_to_position_key", sa.String(160), nullable=True),
        sa.Column("responsibilities", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("autonomy_ceiling", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(24), nullable=False, server_default="planned"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("autonomy_ceiling BETWEEN 0 AND 3", name="ck_workforce_position_autonomy"),
        sa.CheckConstraint("status IN ('planned','active','paused','retired')", name="ck_workforce_position_status"),
        sa.UniqueConstraint("org_id", "workspace_id", "position_key", name="uq_workforce_position_key"),
    )
    op.create_index("ix_workforce_position_scope_department", "workforce_positions", ["org_id", "workspace_id", "department_key"])


def downgrade() -> None:
    op.drop_index("ix_workforce_position_scope_department", table_name="workforce_positions")
    op.drop_table("workforce_positions")
