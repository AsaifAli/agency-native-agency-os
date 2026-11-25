"""Add retainer service-period usage ledger.

Revision ID: j0c6e8f4b327
Revises: i9b5d7f3a216
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "j0c6e8f4b327"
down_revision: Union[str, Sequence[str], None] = "i9b5d7f3a216"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "retainer_service_periods",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contract_id", sa.String(36), sa.ForeignKey("contract_records.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("period_number", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("included_hours", sa.Integer(), nullable=False),
        sa.Column("rollover_in_hours", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("used_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("overage_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("closed_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "workspace_id", "contract_id", "period_number", name="uq_retainer_period_number"),
        sa.CheckConstraint("period_number BETWEEN 1 AND 60", name="ck_retainer_period_number"),
        sa.CheckConstraint("included_hours >= 0 AND rollover_in_hours >= 0", name="ck_retainer_period_allowance"),
        sa.CheckConstraint("used_minutes >= 0 AND overage_minutes >= 0", name="ck_retainer_period_usage"),
        sa.CheckConstraint("status IN ('open','closed')", name="ck_retainer_period_status"),
        sa.CheckConstraint("ends_at > starts_at", name="ck_retainer_period_dates"),
    )
    op.create_index("ix_retainer_period_project_window", "retainer_service_periods", ["org_id", "workspace_id", "project_id", "starts_at", "ends_at"])
    op.create_index("ix_retainer_service_periods_org_id", "retainer_service_periods", ["org_id"])
    op.create_index("ix_retainer_service_periods_workspace_id", "retainer_service_periods", ["workspace_id"])
    op.create_index("ix_retainer_service_periods_contract_id", "retainer_service_periods", ["contract_id"])
    op.create_index("ix_retainer_service_periods_project_id", "retainer_service_periods", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_retainer_service_periods_project_id", table_name="retainer_service_periods")
    op.drop_index("ix_retainer_service_periods_contract_id", table_name="retainer_service_periods")
    op.drop_index("ix_retainer_service_periods_workspace_id", table_name="retainer_service_periods")
    op.drop_index("ix_retainer_service_periods_org_id", table_name="retainer_service_periods")
    op.drop_index("ix_retainer_period_project_window", table_name="retainer_service_periods")
    op.drop_table("retainer_service_periods")
