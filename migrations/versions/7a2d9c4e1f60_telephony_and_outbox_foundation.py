"""Add call records, transcripts and transactional outbox foundation.

Revision ID: 7a2d9c4e1f60
Revises: c91e2d7a4f10
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "7a2d9c4e1f60"
down_revision: Union[str, Sequence[str], None] = "c91e2d7a4f10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "call_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("lead_id", sa.String(36), sa.ForeignKey("leads.id")),
        sa.Column("contact_id", sa.String(36), sa.ForeignKey("contacts.id")),
        sa.Column("direction", sa.String(12), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="planned"),
        sa.Column("provider", sa.String(80), nullable=False, server_default="unconfigured"),
        sa.Column("provider_call_id", sa.String(200)),
        sa.Column("phone_number", sa.String(50), nullable=False),
        sa.Column("purpose", sa.String(240), nullable=False, server_default=""),
        sa.Column("outcome", sa.String(80), nullable=False, server_default=""),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("recording_consent", sa.String(20), nullable=False, server_default="not_requested"),
        sa.Column("recording_object_key", sa.String(500)),
        sa.Column("duration_seconds", sa.Integer()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("direction IN ('inbound','outbound')", name="ck_call_direction"),
        sa.CheckConstraint("status IN ('planned','queued','ringing','in_progress','completed','failed','cancelled')", name="ck_call_status"),
        sa.CheckConstraint("duration_seconds IS NULL OR duration_seconds >= 0", name="ck_call_duration_nonnegative"),
        sa.UniqueConstraint("provider", "provider_call_id", name="uq_call_provider_call_id"),
    )
    op.create_index("ix_call_sessions_org_id", "call_sessions", ["org_id"])
    op.create_index("ix_call_sessions_workspace_id", "call_sessions", ["workspace_id"])
    op.create_index("ix_call_sessions_lead_id", "call_sessions", ["lead_id"])
    op.create_index("ix_call_sessions_contact_id", "call_sessions", ["contact_id"])
    op.create_index("ix_call_sessions_scope_created", "call_sessions", ["org_id", "workspace_id", "created_at"])
    op.create_index("ix_call_sessions_scope_lead", "call_sessions", ["org_id", "workspace_id", "lead_id"])

    op.create_table(
        "call_transcripts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("call_id", sa.String(36), sa.ForeignKey("call_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("transcript_text", sa.Text(), nullable=False),
        sa.Column("language", sa.String(24), nullable=False, server_default="und"),
        sa.Column("source", sa.String(24), nullable=False, server_default="manual"),
        sa.Column("redaction_status", sa.String(24), nullable=False, server_default="unreviewed"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_call_transcripts_org_id", "call_transcripts", ["org_id"])
    op.create_index("ix_call_transcripts_workspace_id", "call_transcripts", ["workspace_id"])
    op.create_index("ix_call_transcripts_call_id", "call_transcripts", ["call_id"])
    op.create_index("ix_call_transcripts_scope_call", "call_transcripts", ["org_id", "workspace_id", "call_id"])

    op.create_table(
        "outbox_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id")),
        sa.Column("event_type", sa.String(160), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("aggregate_type", sa.String(80), nullable=False),
        sa.Column("aggregate_id", sa.String(36), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('pending','processing','published','dead_letter')", name="ck_outbox_status"),
        sa.UniqueConstraint("idempotency_key", name="uq_outbox_idempotency_key"),
    )
    op.create_index("ix_outbox_events_org_id", "outbox_events", ["org_id"])
    op.create_index("ix_outbox_events_workspace_id", "outbox_events", ["workspace_id"])
    op.create_index("ix_outbox_dispatch", "outbox_events", ["status", "available_at"])


def downgrade() -> None:
    op.drop_table("outbox_events")
    op.drop_table("call_transcripts")
    op.drop_table("call_sessions")
