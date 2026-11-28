"""Founder-governed private operations records; model/runtime state stays outside this domain."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

def _uid() -> str: return str(uuid.uuid4())
def _now() -> datetime: return datetime.now(timezone.utc)

class KnowledgeItem(Base):
    """Immutable version row for approved, workspace-governed knowledge."""
    __tablename__ = "knowledge_items"
    __table_args__ = (
        UniqueConstraint("org_id", "workspace_id", "key", "version", name="uq_knowledge_item_version"),
        ForeignKeyConstraint(["org_id", "workspace_id", "client_id"], ["clients.org_id", "clients.workspace_id", "clients.id"],
                             ondelete="RESTRICT", name="fk_knowledge_client_scope"),
        Index("ix_knowledge_items_scope_key", "org_id", "workspace_id", "key", "version"),
        Index("ix_knowledge_items_scope_client", "org_id", "workspace_id", "client_id"),
        CheckConstraint("classification IN ('public','internal','confidential','restricted')", name="ck_knowledge_classification"),
        CheckConstraint("status IN ('draft','approved','retired')", name="ck_knowledge_status"),
        CheckConstraint("version >= 1", name="ck_knowledge_version_positive"),
        CheckConstraint("effective_until IS NULL OR effective_until >= effective_from", name="ck_knowledge_effective_window"),
        CheckConstraint("retention_policy IN ('standard','contractual','legal_hold')", name="ck_knowledge_retention_policy"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    key: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(240), nullable=False)
    classification: Mapped[str] = mapped_column(String(24), nullable=False)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    effective_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retention_policy: Mapped[str] = mapped_column(String(24), default="standard", server_default="standard", nullable=False)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="draft", server_default="draft", nullable=False)
    supersedes_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_items.id", ondelete="RESTRICT"))
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

class BusinessDraft(Base):
    """Persisted, source-linked suggestions. Never sends, approves or commits business actions."""
    __tablename__ = "business_drafts"
    __table_args__ = (
        Index("ix_business_drafts_scope_kind_status", "org_id", "workspace_id", "kind", "status"),
        CheckConstraint("kind IN ('front_desk','meeting_proposal','receivable_followup')", name="ck_business_draft_kind"),
        CheckConstraint("status IN ('draft','reviewed','rejected')", name="ck_business_draft_status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    source_refs: Mapped[list] = mapped_column(JSON, nullable=False)
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="draft", server_default="draft", nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class LearningCandidate(Base):
    """Evidence-backed workspace lesson awaiting founder-controlled promotion."""
    __tablename__ = "learning_candidates"
    __table_args__ = (
        UniqueConstraint("org_id", "workspace_id", "idempotency_key", name="uq_learning_candidate_idempotency"),
        Index("ix_learning_candidate_scope_status", "org_id", "workspace_id", "status", "created_at"),
        CheckConstraint("status IN ('pending_review','promoted','rejected')", name="ck_learning_candidate_status"),
        CheckConstraint("data_class IN ('synthetic','public','internal')", name="ck_learning_candidate_data_class"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_learning_candidate_confidence"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_summary: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(240), nullable=False)
    data_class: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending_review", server_default="pending_review", nullable=False)
    knowledge_item_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_items.id", ondelete="RESTRICT"))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
