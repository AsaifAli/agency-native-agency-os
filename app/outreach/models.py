"""Governed outbound communications metadata; no provider credentials or send execution."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class OutboundSender(Base):
    __tablename__ = "outbound_senders"
    __table_args__ = (
        UniqueConstraint("org_id", "workspace_id", "email_address", name="uq_outbound_sender_email"),
        UniqueConstraint("org_id", "workspace_id", "id", name="uq_outbound_senders_scope_id"),
        ForeignKeyConstraint(
            ["org_id", "workspace_id"], ["workspaces.org_id", "workspaces.id"],
            ondelete="CASCADE", name="fk_outbound_senders_workspace_scope",
        ),
        Index("ix_outbound_senders_scope_status", "org_id", "workspace_id", "status"),
        CheckConstraint("status IN ('draft','active','paused')", name="ck_outbound_sender_status"),
        CheckConstraint("max_per_hour >= 1 AND max_per_hour <= 100 AND max_per_day >= 1 AND max_per_day <= 1000", name="ck_outbound_sender_rate_limits"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    email_address: Mapped[str] = mapped_column(String(320), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="draft", server_default="draft", nullable=False)
    max_per_hour: Mapped[int] = mapped_column(Integer, default=10, server_default="10", nullable=False)
    max_per_day: Mapped[int] = mapped_column(Integer, default=50, server_default="50", nullable=False)
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class CommunicationConsent(Base):
    """Append-only channel-specific consent or reviewed legal-basis evidence."""
    __tablename__ = "communication_consents"
    __table_args__ = (
        UniqueConstraint("org_id", "workspace_id", "id", name="uq_communication_consents_scope_id"),
        ForeignKeyConstraint(
            ["org_id", "workspace_id"], ["workspaces.org_id", "workspaces.id"],
            ondelete="CASCADE", name="fk_communication_consents_workspace_scope",
        ),
        ForeignKeyConstraint(
            ["org_id", "workspace_id", "contact_id"],
            ["contacts.org_id", "contacts.workspace_id", "contacts.id"],
            ondelete="CASCADE", name="fk_communication_consents_contact_scope",
        ),
        Index("ix_communication_consents_latest", "org_id", "workspace_id", "contact_id", "channel", "recorded_at"),
        CheckConstraint("channel IN ('email','phone','sms')", name="ck_communication_consent_channel"),
        CheckConstraint("status IN ('unknown','granted','legitimate_interest_reviewed','withdrawn')", name="ck_communication_consent_status"),
        CheckConstraint("legal_basis IN ('consent','legitimate_interest','contractual','other')", name="ck_communication_consent_basis"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    legal_basis: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(160), nullable=False)
    evidence_reference: Mapped[str] = mapped_column(String(240), default="", server_default="", nullable=False)
    review_note: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    recorded_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class CommunicationBlock(Base):
    """Current stop-state for a contact/channel; release is a separate founder action."""
    __tablename__ = "communication_blocks"
    __table_args__ = (
        UniqueConstraint("org_id", "workspace_id", "contact_id", "channel", name="uq_communication_block_contact_channel"),
        ForeignKeyConstraint(
            ["org_id", "workspace_id"], ["workspaces.org_id", "workspaces.id"],
            ondelete="CASCADE", name="fk_communication_blocks_workspace_scope",
        ),
        ForeignKeyConstraint(
            ["org_id", "workspace_id", "contact_id"],
            ["contacts.org_id", "contacts.workspace_id", "contacts.id"],
            ondelete="CASCADE", name="fk_communication_blocks_contact_scope",
        ),
        Index("ix_communication_blocks_scope_status", "org_id", "workspace_id", "status"),
        CheckConstraint("channel IN ('email','phone','sms')", name="ck_communication_block_channel"),
        CheckConstraint("status IN ('active','released')", name="ck_communication_block_status"),
        CheckConstraint("reason IN ('reply','opt_out','bounce','manual')", name="ck_communication_block_reason"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active", nullable=False)
    reason: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    recorded_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    released_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    release_note: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)


class OutboundMessage(Base):
    __tablename__ = "outbound_messages"
    __table_args__ = (
        UniqueConstraint("org_id", "workspace_id", "id", name="uq_outbound_messages_scope_id"),
        ForeignKeyConstraint(
            ["org_id", "workspace_id"], ["workspaces.org_id", "workspaces.id"],
            ondelete="CASCADE", name="fk_outbound_messages_workspace_scope",
        ),
        ForeignKeyConstraint(
            ["org_id", "workspace_id", "sender_id"],
            ["outbound_senders.org_id", "outbound_senders.workspace_id", "outbound_senders.id"],
            ondelete="RESTRICT", name="fk_outbound_messages_sender_scope",
        ),
        ForeignKeyConstraint(
            ["org_id", "workspace_id", "contact_id"],
            ["contacts.org_id", "contacts.workspace_id", "contacts.id"],
            ondelete="RESTRICT", name="fk_outbound_messages_contact_scope",
        ),
        ForeignKeyConstraint(
            ["org_id", "workspace_id", "lead_id"],
            ["leads.org_id", "leads.workspace_id", "leads.id"],
            ondelete="RESTRICT", name="fk_outbound_messages_lead_scope",
        ),
        ForeignKeyConstraint(
            ["org_id", "workspace_id", "consent_id"],
            ["communication_consents.org_id", "communication_consents.workspace_id", "communication_consents.id"],
            ondelete="RESTRICT", name="fk_outbound_messages_consent_scope",
        ),
        ForeignKeyConstraint(
            ["org_id", "workspace_id", "approval_id"],
            ["approvals.org_id", "approvals.workspace_id", "approvals.id"],
            ondelete="RESTRICT", name="fk_outbound_messages_approval_scope",
        ),
        Index("ix_outbound_messages_scope_status", "org_id", "workspace_id", "status"),
        Index("ix_outbound_messages_sender_queued", "org_id", "workspace_id", "sender_id", "queued_at"),
        Index("ix_outbound_messages_contact", "org_id", "workspace_id", "contact_id", "created_at"),
        CheckConstraint("channel IN ('email')", name="ck_outbound_message_channel"),
        CheckConstraint("status IN ('draft','pending_approval','rejected','queued','sent','delivered','replied','opted_out','bounced','failed','cancelled','suppressed')", name="ck_outbound_message_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_id: Mapped[str] = mapped_column(ForeignKey("outbound_senders.id", ondelete="RESTRICT"), nullable=False, index=True)
    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id", ondelete="RESTRICT"), nullable=False, index=True)
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id", ondelete="RESTRICT"), nullable=True, index=True)
    channel: Mapped[str] = mapped_column(String(16), default="email", server_default="email", nullable=False)
    recipient: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(240), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    purpose: Mapped[str] = mapped_column(String(240), default="", server_default="", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", server_default="draft", nullable=False)
    consent_id: Mapped[str | None] = mapped_column(ForeignKey("communication_consents.id"), nullable=True)
    consent_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    sender_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    approval_id: Mapped[str | None] = mapped_column(ForeignKey("approvals.id"), nullable=True)
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(240), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stop_reason: Mapped[str] = mapped_column(String(80), default="", server_default="", nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class OutboundMessageEvent(Base):
    __tablename__ = "outbound_message_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["org_id", "workspace_id"], ["workspaces.org_id", "workspaces.id"],
            ondelete="CASCADE", name="fk_outbound_message_events_workspace_scope",
        ),
        ForeignKeyConstraint(
            ["org_id", "workspace_id", "message_id"],
            ["outbound_messages.org_id", "outbound_messages.workspace_id", "outbound_messages.id"],
            ondelete="CASCADE", name="fk_outbound_message_events_message_scope",
        ),
        UniqueConstraint("org_id", "workspace_id", "external_event_id", name="uq_outbound_external_event"),
        Index("ix_outbound_message_events_scope", "org_id", "workspace_id", "message_id", "occurred_at"),
        CheckConstraint("event_type IN ('reply','opt_out','bounce','delivered','failed')", name="ck_outbound_event_type"),
        CheckConstraint("source IN ('manual','provider')", name="ck_outbound_event_source"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id: Mapped[str] = mapped_column(ForeignKey("outbound_messages.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    external_event_id: Mapped[str | None] = mapped_column(String(240), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    recorded_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
