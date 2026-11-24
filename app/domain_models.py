"""Revenue and Delivery domain models.

All records are organization- and workspace-scoped. This module is imported by
Alembic's environment so metadata autogeneration sees every model.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text,
    UniqueConstraint, CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Client(Base):
    __tablename__ = "clients"
    __table_args__ = (
        UniqueConstraint("org_id", "workspace_id", "external_key",
                         name="uq_client_workspace_external_key"),
        Index("ix_clients_scope_status", "org_id", "workspace_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(240))
    external_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    industry: Mapped[str] = mapped_column(String(120), default="", server_default="", nullable=False)
    website: Mapped[str] = mapped_column(String(500), default="", server_default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="prospect", server_default="prospect", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (
        Index("ix_contacts_scope_client", "org_id", "workspace_id", "client_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    client_id: Mapped[str | None] = mapped_column(ForeignKey("clients.id"), nullable=True, index=True)
    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    last_name: Mapped[str] = mapped_column(String(120), default="", server_default="", nullable=False)
    email: Mapped[str] = mapped_column(String(320), default="", server_default="", nullable=False)
    phone: Mapped[str] = mapped_column(String(50), default="", server_default="", nullable=False)
    job_title: Mapped[str] = mapped_column(String(160), default="", server_default="", nullable=False)
    source: Mapped[str] = mapped_column(String(120), default="", server_default="", nullable=False)
    consent_status: Mapped[str] = mapped_column(String(32), default="unknown", server_default="unknown", nullable=False)
    phone_call_consent_status: Mapped[str] = mapped_column(String(24), default="unknown", server_default="unknown", nullable=False)
    phone_call_consent_source: Mapped[str] = mapped_column(String(200), default="", server_default="", nullable=False)
    phone_call_consent_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (
        Index("ix_leads_scope_stage_created", "org_id", "workspace_id", "stage", "created_at"),
        UniqueConstraint("org_id", "workspace_id", "source", "external_key", name="uq_lead_external_source_key"),
        CheckConstraint("score >= 0 AND score <= 100", name="ck_lead_score_range"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    client_id: Mapped[str | None] = mapped_column(ForeignKey("clients.id"), nullable=True, index=True)
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("contacts.id"), nullable=True, index=True)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    contact_name: Mapped[str] = mapped_column(String(200), default="", server_default="", nullable=False)
    email: Mapped[str] = mapped_column(String(320), default="", server_default="", nullable=False)
    source: Mapped[str] = mapped_column(String(120), default="", server_default="", nullable=False)
    external_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    stage: Mapped[str] = mapped_column(String(32), default="new", server_default="new", nullable=False)
    score: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    qualification_notes: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    suppression_reason: Mapped[str] = mapped_column(String(240), default="", server_default="", nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class Opportunity(Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        Index("ix_opportunities_scope_stage", "org_id", "workspace_id", "stage"),
        CheckConstraint("amount_minor >= 0", name="ck_opportunity_amount_nonnegative"),
        CheckConstraint("probability >= 0 AND probability <= 100", name="ck_opportunity_probability_range"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    client_id: Mapped[str | None] = mapped_column(ForeignKey("clients.id"), nullable=True, index=True)
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), default="qualification", server_default="qualification", nullable=False)
    amount_minor: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", server_default="INR", nullable=False)
    probability: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    expected_close_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        Index("ix_projects_scope_status", "org_id", "workspace_id", "status"),
        CheckConstraint("budget_minor >= 0", name="ck_project_budget_nonnegative"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    client_id: Mapped[str | None] = mapped_column(ForeignKey("clients.id"), nullable=True, index=True)
    opportunity_id: Mapped[str | None] = mapped_column(ForeignKey("opportunities.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="planned", server_default="planned", nullable=False)
    priority: Mapped[str] = mapped_column(String(16), default="normal", server_default="normal", nullable=False)
    budget_minor: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    contract_value_minor: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    estimated_hours: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", server_default="INR", nullable=False)
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class Milestone(Base):
    __tablename__ = "milestones"
    __table_args__ = (
        Index("ix_milestones_scope_project", "org_id", "workspace_id", "project_id"),
        CheckConstraint("sort_order >= 0", name="ck_milestone_sort_order_nonnegative"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", server_default="pending", nullable=False)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
