"""Machine identities and bounded execution sessions owned by Agency OS."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

def _uid() -> str:
    return str(uuid.uuid4())

def _now() -> datetime:
    return datetime.now(timezone.utc)

class MachineIdentity(Base):
    __tablename__ = "machine_identities"
    __table_args__ = (
        UniqueConstraint("org_id", "workspace_id", "id", name="uq_machine_identity_scope_id"),
        UniqueConstraint("token_hash", name="uq_machine_identity_token_hash"),
        ForeignKeyConstraint(["org_id", "workspace_id"], ["workspaces.org_id", "workspaces.id"], ondelete="CASCADE", name="fk_machine_identity_workspace_scope"),
        CheckConstraint("subject_type IN ('agent','worker','service')", name="ck_machine_identity_subject_type"),
        Index("ix_machine_identity_scope_revoked", "org_id", "workspace_id", "revoked_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(16), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(36), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    token_prefix: Mapped[str] = mapped_column(String(48), nullable=False)
    scopes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    allowed_data_classes: Mapped[list] = mapped_column(JSON, default=lambda: ["synthetic"], nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

class AgentSession(Base):
    __tablename__ = "agent_sessions"
    __table_args__ = (
        ForeignKeyConstraint(["org_id", "workspace_id", "machine_identity_id"], ["machine_identities.org_id", "machine_identities.workspace_id", "machine_identities.id"], ondelete="CASCADE", name="fk_agent_session_identity_scope"),
        CheckConstraint("status IN ('active','cancelled','expired','closed')", name="ck_agent_session_status"),
        CheckConstraint("data_class IN ('synthetic','public','commercial','confidential','regulated')", name="ck_agent_session_data_class"),
        Index("ix_agent_session_scope_status_expiry", "org_id", "workspace_id", "status", "expires_at"),
        Index("ix_agent_session_identity_status", "machine_identity_id", "status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False)
    machine_identity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    purpose: Mapped[str] = mapped_column(String(240), nullable=False)
    data_class: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
