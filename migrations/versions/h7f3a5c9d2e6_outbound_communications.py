"""Create governed outbound communication consent, suppression and queue records.

Revision ID: h7f3a5c9d2e6
Revises: g6e2f4a8c195
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "h7f3a5c9d2e6"
down_revision: Union[str, Sequence[str], None] = "g6e2f4a8c195"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outbound_senders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("email_address", sa.String(320), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("max_per_hour", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("max_per_day", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("approved_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "workspace_id", "email_address", name="uq_outbound_sender_email"),
        sa.CheckConstraint("status IN ('draft','active','paused')", name="ck_outbound_sender_status"),
        sa.CheckConstraint("max_per_hour >= 1 AND max_per_hour <= 100 AND max_per_day >= 1 AND max_per_day <= 1000", name="ck_outbound_sender_rate_limits"),
    )
    op.create_index("ix_outbound_senders_scope_status", "outbound_senders", ["org_id", "workspace_id", "status"])
    op.create_index("ix_outbound_senders_org_id", "outbound_senders", ["org_id"])
    op.create_index("ix_outbound_senders_workspace_id", "outbound_senders", ["workspace_id"])

    op.create_table(
        "communication_consents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contact_id", sa.String(36), sa.ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("legal_basis", sa.String(32), nullable=False),
        sa.Column("source", sa.String(160), nullable=False),
        sa.Column("evidence_reference", sa.String(240), nullable=False, server_default=""),
        sa.Column("review_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("channel IN ('email','phone','sms')", name="ck_communication_consent_channel"),
        sa.CheckConstraint("status IN ('unknown','granted','legitimate_interest_reviewed','withdrawn')", name="ck_communication_consent_status"),
        sa.CheckConstraint("legal_basis IN ('consent','legitimate_interest','contractual','other')", name="ck_communication_consent_basis"),
    )
    op.create_index("ix_communication_consents_latest", "communication_consents", ["org_id", "workspace_id", "contact_id", "channel", "recorded_at"])
    op.create_index("ix_communication_consents_org_id", "communication_consents", ["org_id"])
    op.create_index("ix_communication_consents_workspace_id", "communication_consents", ["workspace_id"])
    op.create_index("ix_communication_consents_contact_id", "communication_consents", ["contact_id"])

    op.create_table(
        "communication_blocks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contact_id", sa.String(36), sa.ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("reason", sa.String(16), nullable=False),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("recorded_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("release_note", sa.Text(), nullable=False, server_default=""),
        sa.UniqueConstraint("org_id", "workspace_id", "contact_id", "channel", name="uq_communication_block_contact_channel"),
        sa.CheckConstraint("channel IN ('email','phone','sms')", name="ck_communication_block_channel"),
        sa.CheckConstraint("status IN ('active','released')", name="ck_communication_block_status"),
        sa.CheckConstraint("reason IN ('reply','opt_out','bounce','manual')", name="ck_communication_block_reason"),
    )
    op.create_index("ix_communication_blocks_scope_status", "communication_blocks", ["org_id", "workspace_id", "status"])
    op.create_index("ix_communication_blocks_org_id", "communication_blocks", ["org_id"])
    op.create_index("ix_communication_blocks_workspace_id", "communication_blocks", ["workspace_id"])
    op.create_index("ix_communication_blocks_contact_id", "communication_blocks", ["contact_id"])

    op.create_table(
        "outbound_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sender_id", sa.String(36), sa.ForeignKey("outbound_senders.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("contact_id", sa.String(36), sa.ForeignKey("contacts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("lead_id", sa.String(36), sa.ForeignKey("leads.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("channel", sa.String(16), nullable=False, server_default="email"),
        sa.Column("recipient", sa.String(320), nullable=False),
        sa.Column("subject", sa.String(240), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("purpose", sa.String(240), nullable=False, server_default=""),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("consent_id", sa.String(36), sa.ForeignKey("communication_consents.id"), nullable=True),
        sa.Column("consent_snapshot", sa.JSON(), nullable=False),
        sa.Column("sender_snapshot", sa.JSON(), nullable=False),
        sa.Column("approval_id", sa.String(36), sa.ForeignKey("approvals.id"), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_message_id", sa.String(240), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stop_reason", sa.String(80), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("channel IN ('email')", name="ck_outbound_message_channel"),
        sa.CheckConstraint("status IN ('draft','pending_approval','queued','sent','delivered','replied','opted_out','bounced','failed','cancelled','suppressed')", name="ck_outbound_message_status"),
    )
    op.create_index("ix_outbound_messages_scope_status", "outbound_messages", ["org_id", "workspace_id", "status"])
    op.create_index("ix_outbound_messages_sender_queued", "outbound_messages", ["org_id", "workspace_id", "sender_id", "queued_at"])
    op.create_index("ix_outbound_messages_contact", "outbound_messages", ["org_id", "workspace_id", "contact_id", "created_at"])
    op.create_index("ix_outbound_messages_org_id", "outbound_messages", ["org_id"])
    op.create_index("ix_outbound_messages_workspace_id", "outbound_messages", ["workspace_id"])
    op.create_index("ix_outbound_messages_sender_id", "outbound_messages", ["sender_id"])
    op.create_index("ix_outbound_messages_contact_id", "outbound_messages", ["contact_id"])
    op.create_index("ix_outbound_messages_lead_id", "outbound_messages", ["lead_id"])

    op.create_table(
        "outbound_message_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_id", sa.String(36), sa.ForeignKey("outbound_messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(16), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("external_event_id", sa.String(240), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("recorded_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "workspace_id", "external_event_id", name="uq_outbound_external_event"),
        sa.CheckConstraint("event_type IN ('reply','opt_out','bounce','delivered','failed')", name="ck_outbound_event_type"),
        sa.CheckConstraint("source IN ('manual','provider')", name="ck_outbound_event_source"),
    )
    op.create_index("ix_outbound_message_events_scope", "outbound_message_events", ["org_id", "workspace_id", "message_id", "occurred_at"])
    op.create_index("ix_outbound_message_events_org_id", "outbound_message_events", ["org_id"])
    op.create_index("ix_outbound_message_events_workspace_id", "outbound_message_events", ["workspace_id"])
    op.create_index("ix_outbound_message_events_message_id", "outbound_message_events", ["message_id"])


def downgrade() -> None:
    op.drop_index("ix_outbound_message_events_message_id", table_name="outbound_message_events")
    op.drop_index("ix_outbound_message_events_workspace_id", table_name="outbound_message_events")
    op.drop_index("ix_outbound_message_events_org_id", table_name="outbound_message_events")
    op.drop_index("ix_outbound_message_events_scope", table_name="outbound_message_events")
    op.drop_table("outbound_message_events")
    op.drop_index("ix_outbound_messages_lead_id", table_name="outbound_messages")
    op.drop_index("ix_outbound_messages_contact_id", table_name="outbound_messages")
    op.drop_index("ix_outbound_messages_sender_id", table_name="outbound_messages")
    op.drop_index("ix_outbound_messages_workspace_id", table_name="outbound_messages")
    op.drop_index("ix_outbound_messages_org_id", table_name="outbound_messages")
    op.drop_index("ix_outbound_messages_contact", table_name="outbound_messages")
    op.drop_index("ix_outbound_messages_sender_queued", table_name="outbound_messages")
    op.drop_index("ix_outbound_messages_scope_status", table_name="outbound_messages")
    op.drop_table("outbound_messages")
    op.drop_index("ix_communication_blocks_contact_id", table_name="communication_blocks")
    op.drop_index("ix_communication_blocks_workspace_id", table_name="communication_blocks")
    op.drop_index("ix_communication_blocks_org_id", table_name="communication_blocks")
    op.drop_index("ix_communication_blocks_scope_status", table_name="communication_blocks")
    op.drop_table("communication_blocks")
    op.drop_index("ix_communication_consents_contact_id", table_name="communication_consents")
    op.drop_index("ix_communication_consents_workspace_id", table_name="communication_consents")
    op.drop_index("ix_communication_consents_org_id", table_name="communication_consents")
    op.drop_index("ix_communication_consents_latest", table_name="communication_consents")
    op.drop_table("communication_consents")
    op.drop_index("ix_outbound_senders_workspace_id", table_name="outbound_senders")
    op.drop_index("ix_outbound_senders_org_id", table_name="outbound_senders")
    op.drop_index("ix_outbound_senders_scope_status", table_name="outbound_senders")
    op.drop_table("outbound_senders")
