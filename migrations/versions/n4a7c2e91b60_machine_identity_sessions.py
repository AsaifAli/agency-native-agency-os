"""Add scoped machine identities and expiring agent sessions.

Revision ID: n4a7c2e91b60
Revises: m3f9c2a7e514
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "n4a7c2e91b60"
down_revision: Union[str, Sequence[str], None] = "m3f9c2a7e514"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "machine_identities",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("subject_type", sa.String(16), nullable=False),
        sa.Column("subject_id", sa.String(36), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("token_prefix", sa.String(48), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("allowed_data_classes", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "workspace_id", "id", name="uq_machine_identity_scope_id"),
        sa.UniqueConstraint("token_hash", name="uq_machine_identity_token_hash"),
        sa.ForeignKeyConstraint(["org_id", "workspace_id"], ["workspaces.org_id", "workspaces.id"], ondelete="CASCADE", name="fk_machine_identity_workspace_scope"),
        sa.CheckConstraint("subject_type IN ('agent','worker','service')", name="ck_machine_identity_subject_type"),
    )
    op.create_index("ix_machine_identity_scope_revoked", "machine_identities", ["org_id", "workspace_id", "revoked_at"])
    op.create_table(
        "agent_sessions",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("machine_identity_id", sa.String(36), nullable=False),
        sa.Column("purpose", sa.String(240), nullable=False),
        sa.Column("data_class", sa.String(20), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id", "workspace_id", "machine_identity_id"], ["machine_identities.org_id", "machine_identities.workspace_id", "machine_identities.id"], ondelete="CASCADE", name="fk_agent_session_identity_scope"),
        sa.CheckConstraint("status IN ('active','cancelled','expired','closed')", name="ck_agent_session_status"),
        sa.CheckConstraint("data_class IN ('synthetic','public','commercial','confidential','regulated')", name="ck_agent_session_data_class"),
    )
    op.create_index("ix_agent_session_scope_status_expiry", "agent_sessions", ["org_id", "workspace_id", "status", "expires_at"])
    op.create_index("ix_agent_session_identity_status", "agent_sessions", ["machine_identity_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_agent_session_identity_status", table_name="agent_sessions")
    op.drop_index("ix_agent_session_scope_status_expiry", table_name="agent_sessions")
    op.drop_table("agent_sessions")
    op.drop_index("ix_machine_identity_scope_revoked", table_name="machine_identities")
    op.drop_table("machine_identities")
