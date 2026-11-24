"""Create founder-managed service catalogue.

Revision ID: d3a7c9e1b542
Revises: c7b1a4e9d630
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "d3a7c9e1b542"
down_revision: Union[str, Sequence[str], None] = "c7b1a4e9d630"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "service_offerings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(60), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("service_line", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("pricing_model", sa.String(24), nullable=False),
        sa.Column("indicative_price_minor", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("typical_duration_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("target_outcomes", sa.JSON(), nullable=False),
        sa.Column("deliverables", sa.JSON(), nullable=False),
        sa.Column("required_inputs", sa.JSON(), nullable=False),
        sa.Column("exclusions", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "workspace_id", "code", name="uq_service_offering_workspace_code"),
        sa.CheckConstraint("status IN ('draft','active','retired')", name="ck_service_offering_status"),
        sa.CheckConstraint("pricing_model IN ('fixed','hourly','retainer','custom')", name="ck_service_offering_pricing_model"),
        sa.CheckConstraint("indicative_price_minor IS NULL OR indicative_price_minor >= 0", name="ck_service_offering_price_nonnegative"),
        sa.CheckConstraint("typical_duration_days >= 0 AND typical_duration_days <= 3650", name="ck_service_offering_duration"),
    )
    op.create_index("ix_service_offerings_scope_status", "service_offerings", ["org_id", "workspace_id", "status"])
    op.create_index("ix_service_offerings_org_id", "service_offerings", ["org_id"])
    op.create_index("ix_service_offerings_workspace_id", "service_offerings", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_service_offerings_workspace_id", table_name="service_offerings")
    op.drop_index("ix_service_offerings_org_id", table_name="service_offerings")
    op.drop_index("ix_service_offerings_scope_status", table_name="service_offerings")
    op.drop_table("service_offerings")
