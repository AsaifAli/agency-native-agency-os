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

class BrowserSession(Base):
    """Revocable browser login session; only a digest of the JWT jti is stored."""
    __tablename__ = "browser_sessions"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_browser_session_token_hash"),
        Index("ix_browser_session_user_revoked", "user_id", "revoked_at"),
        Index("ix_browser_session_expiry", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


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
        UniqueConstraint("org_id", "workspace_id", "id", name="uq_agent_session_scope_id"),
        UniqueConstraint("org_id", "workspace_id", "machine_identity_id", "id", name="uq_agent_session_identity_scope_id"),
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
    metadata_purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ToolInvocation(Base):
    """Durable, idempotent record of a machine-initiated OS tool invocation."""
    __tablename__ = "tool_invocations"
    __table_args__ = (
        UniqueConstraint("org_id", "workspace_id", "idempotency_key", name="uq_tool_invocation_scope_idempotency"),
        ForeignKeyConstraint(["org_id", "workspace_id"], ["workspaces.org_id", "workspaces.id"], ondelete="CASCADE", name="fk_tool_invocation_workspace_scope"),
        ForeignKeyConstraint(["org_id", "workspace_id", "machine_identity_id"], ["machine_identities.org_id", "machine_identities.workspace_id", "machine_identities.id"], ondelete="CASCADE", name="fk_tool_invocation_identity_scope"),
        ForeignKeyConstraint(["org_id", "workspace_id", "session_id"], ["agent_sessions.org_id", "agent_sessions.workspace_id", "agent_sessions.id"], ondelete="CASCADE", name="fk_tool_invocation_session_scope"),
        CheckConstraint("status IN ('succeeded','failed')", name="ck_tool_invocation_status"),
        Index("ix_tool_invocation_scope_created", "org_id", "workspace_id", "created_at"),
        Index("ix_tool_invocation_identity_tool", "machine_identity_id", "tool_key", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False)
    machine_identity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    tool_key: Mapped[str] = mapped_column(String(120), nullable=False)
    tool_version: Mapped[str] = mapped_column(String(40), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload_purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MachineSessionCredential(Base):
    """One-time bearer credential bound to exactly one active AgentSession."""

    __tablename__ = "machine_session_credentials"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_machine_session_credential_token_hash"),
        UniqueConstraint(
            "org_id", "workspace_id", "session_id", "credential_version",
            name="uq_machine_session_credential_version",
        ),
        ForeignKeyConstraint(
            ["org_id", "workspace_id", "machine_identity_id", "session_id"],
            [
                "agent_sessions.org_id",
                "agent_sessions.workspace_id",
                "agent_sessions.machine_identity_id",
                "agent_sessions.id",
            ],
            ondelete="CASCADE",
            name="fk_machine_session_credential_session_identity_scope",
        ),
        CheckConstraint("credential_version >= 1", name="ck_machine_session_credential_version"),
        CheckConstraint("request_count_window >= 0", name="ck_machine_session_credential_request_count"),
        CheckConstraint("provider_credential_status IN ('not_created','active','delete_pending','deleted','failed')", name="ck_machine_session_credential_provider_status"),
        Index(
            "ix_machine_session_credential_session_revoked",
            "org_id", "workspace_id", "session_id", "revoked_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(String(36), nullable=False)
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False)
    machine_identity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    token_prefix: Mapped[str] = mapped_column(String(80), nullable=False)
    credential_version: Mapped[int] = mapped_column(default=1, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    request_window_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    request_count_window: Mapped[int] = mapped_column(default=0, nullable=False)
    provider_vault_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    provider_credential_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    provider_credential_status: Mapped[str] = mapped_column(String(24), default="not_created", nullable=False)
    provider_credential_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_credential_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
