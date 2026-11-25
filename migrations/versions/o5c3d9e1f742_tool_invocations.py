"""Add durable idempotent OS tool invocation records.

Revision ID: o5c3d9e1f742
Revises: n4a7c2e91b60
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "o5c3d9e1f742"
down_revision: Union[str, Sequence[str], None] = "n4a7c2e91b60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("agent_sessions") as batch:
        batch.create_unique_constraint("uq_agent_session_scope_id", ["org_id", "workspace_id", "id"])

    op.create_table(
        "tool_invocations",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("machine_identity_id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("tool_key", sa.String(120), nullable=False),
        sa.Column("tool_version", sa.String(40), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("org_id", "workspace_id", "idempotency_key", name="uq_tool_invocation_scope_idempotency"),
        sa.ForeignKeyConstraint(["org_id", "workspace_id"], ["workspaces.org_id", "workspaces.id"], ondelete="CASCADE", name="fk_tool_invocation_workspace_scope"),
        sa.ForeignKeyConstraint(["org_id", "workspace_id", "machine_identity_id"], ["machine_identities.org_id", "machine_identities.workspace_id", "machine_identities.id"], ondelete="CASCADE", name="fk_tool_invocation_identity_scope"),
        sa.ForeignKeyConstraint(["org_id", "workspace_id", "session_id"], ["agent_sessions.org_id", "agent_sessions.workspace_id", "agent_sessions.id"], ondelete="CASCADE", name="fk_tool_invocation_session_scope"),
        sa.CheckConstraint("status IN ('succeeded','failed')", name="ck_tool_invocation_status"),
    )
    op.create_index("ix_tool_invocation_scope_created", "tool_invocations", ["org_id", "workspace_id", "created_at"])
    op.create_index("ix_tool_invocation_identity_tool", "tool_invocations", ["machine_identity_id", "tool_key", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_tool_invocation_identity_tool", table_name="tool_invocations")
    op.drop_index("ix_tool_invocation_scope_created", table_name="tool_invocations")
    op.drop_table("tool_invocations")
    with op.batch_alter_table("agent_sessions") as batch:
        batch.drop_constraint("uq_agent_session_scope_id", type_="unique")
