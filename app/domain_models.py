"""Revenue and Delivery domain models.

All records are organization- and workspace-scoped. This module is imported by
Alembic's environment so metadata autogeneration sees every model.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, JSON, String, Text,
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
        UniqueConstraint("org_id", "workspace_id", "id", name="uq_clients_scope_id"),
        ForeignKeyConstraint(
            ["org_id", "workspace_id"], ["workspaces.org_id", "workspaces.id"],
            ondelete="CASCADE", name="fk_clients_workspace_scope",
        ),
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
        UniqueConstraint("org_id", "workspace_id", "id", name="uq_contacts_scope_id"),
        ForeignKeyConstraint(
            ["org_id", "workspace_id"], ["workspaces.org_id", "workspaces.id"],
            ondelete="CASCADE", name="fk_contacts_workspace_scope",
        ),
        ForeignKeyConstraint(
            ["org_id", "workspace_id", "client_id"],
            ["clients.org_id", "clients.workspace_id", "clients.id"],
            ondelete="RESTRICT", name="fk_contacts_client_scope",
        ),
        Index("ix_contacts_scope_client", "org_id", "workspace_id", "client_id"),
        CheckConstraint("phone_call_consent_status IN ('unknown','pending','granted','withdrawn')", name="ck_contact_phone_call_consent_status"),
        CheckConstraint("phone_call_consent_status != 'granted' OR (length(trim(phone_call_consent_source)) > 0 AND phone_call_consent_recorded_at IS NOT NULL)", name="ck_contact_phone_call_consent_evidence"),
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


class ContactActivity(Base):
    """Append-only CRM interaction history; never triggers external communication."""
    __tablename__ = "contact_activities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["org_id", "workspace_id"], ["workspaces.org_id", "workspaces.id"],
            ondelete="CASCADE", name="fk_contact_activities_workspace_scope",
        ),
        ForeignKeyConstraint(
            ["org_id", "workspace_id", "contact_id"],
            ["contacts.org_id", "contacts.workspace_id", "contacts.id"],
            ondelete="CASCADE", name="fk_contact_activities_contact_scope",
        ),
        Index("ix_contact_activities_scope_contact_time", "org_id", "workspace_id", "contact_id", "occurred_at"),
        CheckConstraint("activity_type IN ('note','call','email','meeting','task','status_update')", name="ck_contact_activity_type"),
        CheckConstraint("direction IN ('none','inbound','outbound','internal')", name="ck_contact_activity_direction"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True)
    activity_type: Mapped[str] = mapped_column(String(24), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), default="none", server_default="none", nullable=False)
    subject: Mapped[str] = mapped_column(String(240), default="", server_default="", nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    outcome: Mapped[str] = mapped_column(String(240), default="", server_default="", nullable=False)
    source_reference: Mapped[str] = mapped_column(String(200), default="", server_default="", nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (
        UniqueConstraint("org_id", "workspace_id", "id", name="uq_leads_scope_id"),
        ForeignKeyConstraint(
            ["org_id", "workspace_id"], ["workspaces.org_id", "workspaces.id"],
            ondelete="CASCADE", name="fk_leads_workspace_scope",
        ),
        ForeignKeyConstraint(
            ["org_id", "workspace_id", "client_id"],
            ["clients.org_id", "clients.workspace_id", "clients.id"],
            ondelete="RESTRICT", name="fk_leads_client_scope",
        ),
        ForeignKeyConstraint(
            ["org_id", "workspace_id", "contact_id"],
            ["contacts.org_id", "contacts.workspace_id", "contacts.id"],
            ondelete="RESTRICT", name="fk_leads_contact_scope",
        ),
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


class LeadResearchRecord(Base):
    """Append-only, source-backed research findings prepared by a human or agent."""
    __tablename__ = "lead_research_records"
    __table_args__ = (
        Index("ix_lead_research_scope_lead_time", "org_id", "workspace_id", "lead_id", "researched_at"),
        CheckConstraint("fit_score BETWEEN 0 AND 100", name="ck_lead_research_fit_score"),
        CheckConstraint("confidence_score BETWEEN 0 AND 100", name="ck_lead_research_confidence_score"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    fit_score: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, nullable=False)
    buying_signals: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    risks: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    source_references: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    researched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class OutreachDraft(Base):
    """Agent-prepared communication draft; never sends or schedules a message."""
    __tablename__ = "outreach_drafts"
    __table_args__ = (
        Index("ix_outreach_drafts_scope_status", "org_id", "workspace_id", "status"),
        CheckConstraint("channel IN ('email','linkedin','call_script')", name="ck_outreach_draft_channel"),
        CheckConstraint("status IN ('draft','approved_draft','rejected')", name="ck_outreach_draft_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True, index=True)
    channel: Mapped[str] = mapped_column(String(24), nullable=False)
    subject: Mapped[str] = mapped_column(String(240), default="", server_default="", nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    personalization_basis: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    source_research_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", server_default="draft", nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


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


class LeadResearchDraft(Base):
    """Public-source lead research captured by agents for founder review."""
    __tablename__ = "lead_research_drafts"
    __table_args__ = (
        UniqueConstraint("org_id", "workspace_id", "id", name="uq_lead_research_drafts_scope_id"),
        UniqueConstraint("org_id", "workspace_id", "idempotency_key", name="uq_lead_research_draft_idempotency"),
        ForeignKeyConstraint(
            ["org_id", "workspace_id"],
            ["workspaces.org_id", "workspaces.id"],
            ondelete="CASCADE",
            name="fk_lead_research_drafts_workspace_scope",
        ),
        ForeignKeyConstraint(
            ["org_id", "workspace_id", "machine_identity_id"],
            ["machine_identities.org_id", "machine_identities.workspace_id", "machine_identities.id"],
            ondelete="RESTRICT",
            name="fk_lead_research_drafts_machine_identity_scope",
        ),
        CheckConstraint("fit_score BETWEEN 0 AND 100", name="ck_lead_research_draft_fit_score"),
        CheckConstraint("confidence_score BETWEEN 0 AND 100", name="ck_lead_research_draft_confidence_score"),
        CheckConstraint("status IN ('pending_review','approved','rejected')", name="ck_lead_research_draft_status"),
        Index("ix_lead_research_drafts_scope_status_created", "org_id", "workspace_id", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    machine_identity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    source_references: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    fit_score: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, nullable=False)
    buying_signals: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    risks: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending_review", server_default="pending_review", nullable=False)
    review_note: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    reviewed_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
