"""Create append-only CRM contact activity history.

Revision ID: b8d4e6f1a203
Revises: f9c2a6d8e410
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "b8d4e6f1a203"
down_revision: Union[str, Sequence[str], None] = "f9c2a6d8e410"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contact_activities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contact_id", sa.String(36), sa.ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("activity_type", sa.String(24), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False, server_default="none"),
        sa.Column("subject", sa.String(240), nullable=False, server_default=""),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("outcome", sa.String(240), nullable=False, server_default=""),
        sa.Column("source_reference", sa.String(200), nullable=False, server_default=""),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("activity_type IN ('note','call','email','meeting','task','status_update')", name="ck_contact_activity_type"),
        sa.CheckConstraint("direction IN ('none','inbound','outbound','internal')", name="ck_contact_activity_direction"),
    )
    op.create_index("ix_contact_activities_scope_contact_time", "contact_activities", ["org_id", "workspace_id", "contact_id", "occurred_at"])
    op.create_index("ix_contact_activities_org_id", "contact_activities", ["org_id"])
    op.create_index("ix_contact_activities_workspace_id", "contact_activities", ["workspace_id"])
    op.create_index("ix_contact_activities_contact_id", "contact_activities", ["contact_id"])


def downgrade() -> None:
    op.drop_index("ix_contact_activities_contact_id", table_name="contact_activities")
    op.drop_index("ix_contact_activities_workspace_id", table_name="contact_activities")
    op.drop_index("ix_contact_activities_org_id", table_name="contact_activities")
    op.drop_index("ix_contact_activities_scope_contact_time", table_name="contact_activities")
    op.drop_table("contact_activities")
