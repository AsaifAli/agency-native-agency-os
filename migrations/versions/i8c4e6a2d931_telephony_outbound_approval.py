"""Add consent and approval gates for outbound call intent.

Revision ID: i8c4e6a2d931
Revises: h7f3a5c9d2e6
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "i8c4e6a2d931"
down_revision: Union[str, Sequence[str], None] = "h7f3a5c9d2e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_call_status", "call_sessions", type_="check")
    op.add_column("call_sessions", sa.Column("call_authorization", sa.String(32), nullable=False, server_default=""))
    op.add_column("call_sessions", sa.Column("call_authorization_reference", sa.String(240), nullable=False, server_default=""))
    op.add_column("call_sessions", sa.Column("consent_id", sa.String(36), sa.ForeignKey("communication_consents.id"), nullable=True))
    op.add_column("call_sessions", sa.Column("consent_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.add_column("call_sessions", sa.Column("approval_id", sa.String(36), sa.ForeignKey("approvals.id"), nullable=True))
    op.create_index("ix_call_sessions_consent_id", "call_sessions", ["consent_id"])
    op.create_check_constraint(
        "ck_call_status",
        "call_sessions",
        "status IN ('planned','pending_approval','queued','ringing','in_progress','completed','failed','cancelled')",
    )
    op.create_check_constraint(
        "ck_call_authorization",
        "call_sessions",
        "call_authorization IN ('','founder_initiated','requested_callback')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_call_authorization", "call_sessions", type_="check")
    op.drop_constraint("ck_call_status", "call_sessions", type_="check")
    op.drop_index("ix_call_sessions_consent_id", table_name="call_sessions")
    op.drop_column("call_sessions", "approval_id")
    op.drop_column("call_sessions", "consent_snapshot")
    op.drop_column("call_sessions", "consent_id")
    op.drop_column("call_sessions", "call_authorization_reference")
    op.drop_column("call_sessions", "call_authorization")
    op.create_check_constraint(
        "ck_call_status",
        "call_sessions",
        "status IN ('planned','queued','ringing','in_progress','completed','failed','cancelled')",
    )
