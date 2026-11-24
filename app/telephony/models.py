"""Workspace-scoped call records and transactional outbox."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CallSession(Base):
    __tablename__ = "call_sessions"
    __table_args__ = (
        Index("ix_call_sessions_scope_created", "org_id", "workspace_id", "created_at"),
        Index("ix_call_sessions_scope_lead", "org_id", "workspace_id", "lead_id"),
        CheckConstraint("direction IN ('inbound','outbound')", name="ck_call_direction"),
        CheckConstraint("status IN ('planned','queued','ringing','in_progress','completed','failed','cancelled')", name="ck_call_status"),
        CheckConstraint("duration_seconds IS NULL OR duration_seconds >= 0", name="ck_call_duration_nonnegative"),
        UniqueConstraint("provider", "provider_call_id", name="uq_call_provider_call_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id"), nullable=True, index=True)
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("contacts.id"), nullable=True, index=True)
    direction: Mapped[str] = mapped_column(String(12), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="planned", server_default="planned")
    provider: Mapped[str] = mapped_column(String(80), nullable=False, default="unconfigured", server_default="unconfigured")
    provider_call_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone_number: Mapped[str] = mapped_column(String(50), nullable=False)
    purpose: Mapped[str] = mapped_column(String(240), nullable=False, default="", server_default="")
    outcome: Mapped[str] = mapped_column(String(80), nullable=False, default="", server_default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    recording_consent: Mapped[str] = mapped_column(String(20), nullable=False, default="not_requested", server_default="not_requested")
    recording_object_key: Mapped[str | None] = mapped_column(String(500))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class CallTranscript(Base):
    __tablename__ = "call_transcripts"
    __table_args__ = (Index("ix_call_transcripts_scope_call", "org_id", "workspace_id", "call_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    call_id: Mapped[str] = mapped_column(ForeignKey("call_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    transcript_text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(24), nullable=False, default="und", server_default="und")
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="manual", server_default="manual")
    redaction_status: Mapped[str] = mapped_column(String(24), nullable=False, default="unreviewed", server_default="unreviewed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        Index("ix_outbox_dispatch", "status", "available_at"),
        UniqueConstraint("idempotency_key", name="uq_outbox_idempotency_key"),
        CheckConstraint("status IN ('pending','processing','published','dead_letter')", name="ck_outbox_status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    workspace_id: Mapped[str | None] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(160), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    aggregate_type: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(36), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
