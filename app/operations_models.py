"""Lightweight delivery operations: playbooks, scope control, time and costs."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON,
    String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ServicePlaybook(Base):
    __tablename__ = "service_playbooks"
    __table_args__ = (
        Index("ix_playbooks_scope_status", "org_id", "workspace_id", "status"),
        CheckConstraint("status IN ('draft','active','retired')", name="ck_playbook_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    service_line: Mapped[str] = mapped_column(String(80), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="draft", server_default="draft", nullable=False)
    workflow: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    required_inputs: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    deliverables: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    acceptance_criteria: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    security_checks: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class ServiceOffering(Base):
    """Founder-managed service catalogue entry; not a customer contract or commitment."""
    __tablename__ = "service_offerings"
    __table_args__ = (
        UniqueConstraint("org_id", "workspace_id", "code", "version", name="uq_service_offering_workspace_code_version"),
        Index("ix_service_offerings_scope_status", "org_id", "workspace_id", "status"),
        CheckConstraint("status IN ('draft','active','retired')", name="ck_service_offering_status"),
        CheckConstraint("pricing_model IN ('fixed','hourly','retainer','custom')", name="ck_service_offering_pricing_model"),
        CheckConstraint("indicative_price_minor IS NULL OR indicative_price_minor >= 0", name="ck_service_offering_price_nonnegative"),
        CheckConstraint("typical_duration_days >= 0 AND typical_duration_days <= 3650", name="ck_service_offering_duration"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    service_line: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    pricing_model: Mapped[str] = mapped_column(String(24), nullable=False)
    indicative_price_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="INR", server_default="INR", nullable=False)
    typical_duration_days: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    target_outcomes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    deliverables: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    required_inputs: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    exclusions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="draft", server_default="draft", nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class Proposal(Base):
    """Internal proposal draft; approval is required before it can be treated as approved pricing."""
    __tablename__ = "proposals"
    __table_args__ = (
        Index("ix_proposals_scope_status", "org_id", "workspace_id", "status"),
        CheckConstraint("status IN ('draft','pending_approval','approved','rejected','withdrawn')", name="ck_proposal_status"),
        CheckConstraint("amount_minor >= 0", name="ck_proposal_amount_nonnegative"),
        CheckConstraint("validity_days >= 1 AND validity_days <= 180", name="ck_proposal_validity_days"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id", ondelete="RESTRICT"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    service_line: Mapped[str] = mapped_column(String(120), nullable=False)
    scope_summary: Mapped[str] = mapped_column(Text, nullable=False)
    deliverables: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    assumptions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    exclusions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    validity_days: Mapped[int] = mapped_column(Integer, default=30, server_default="30", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", server_default="draft", nullable=False)
    approval_id: Mapped[str | None] = mapped_column(ForeignKey("approvals.id"), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class ContractRecord(Base):
    """Internal contract register. Executed status requires recorded signed evidence."""
    __tablename__ = "contract_records"
    __table_args__ = (
        UniqueConstraint("org_id", "workspace_id", "contract_number", name="uq_contract_number_workspace"),
        Index("ix_contract_records_scope_status", "org_id", "workspace_id", "status"),
        CheckConstraint("status IN ('draft','pending_approval','executed','rejected','terminated')", name="ck_contract_record_status"),
        CheckConstraint("amount_minor >= 0", name="ck_contract_record_amount_nonnegative"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False, index=True)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("proposals.id", ondelete="RESTRICT"), nullable=False, index=True)
    contract_number: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    terms_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", server_default="draft", nullable=False)
    approval_id: Mapped[str | None] = mapped_column(ForeignKey("approvals.id"), nullable=True)
    signed_reference: Mapped[str] = mapped_column(String(240), default="", server_default="", nullable=False)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class ClientOnboarding(Base):
    """Internal client handoff, gated by an executed contract and delivery approval."""
    __tablename__ = "client_onboardings"
    __table_args__ = (
        UniqueConstraint("org_id", "workspace_id", "contract_id", name="uq_onboarding_contract"),
        Index("ix_client_onboardings_scope_status", "org_id", "workspace_id", "status"),
        CheckConstraint("status IN ('preparing','pending_approval','active','paused','completed','cancelled')", name="ck_client_onboarding_status"),
        CheckConstraint("budget_minor >= 0 AND estimated_hours >= 0", name="ck_onboarding_project_plan_nonnegative"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False, index=True)
    contract_id: Mapped[str] = mapped_column(ForeignKey("contract_records.id", ondelete="RESTRICT"), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(24), default="preparing", server_default="preparing", nullable=False)
    approval_id: Mapped[str | None] = mapped_column(ForeignKey("approvals.id"), nullable=True)
    activation_plan: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    project_name: Mapped[str] = mapped_column(String(240), default="", server_default="", nullable=False)
    budget_minor: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    estimated_hours: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class OnboardingChecklistItem(Base):
    __tablename__ = "onboarding_checklist_items"
    __table_args__ = (
        UniqueConstraint("org_id", "workspace_id", "onboarding_id", "code", name="uq_onboarding_item_code"),
        Index("ix_onboarding_items_scope_status", "org_id", "workspace_id", "onboarding_id", "status"),
        CheckConstraint("status IN ('open','completed','waived')", name="ck_onboarding_item_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    onboarding_id: Mapped[str] = mapped_column(ForeignKey("client_onboardings.id", ondelete="CASCADE"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open", server_default="open", nullable=False)
    completion_note: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    completed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    waived_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    waived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class ScopeChangeRequest(Base):
    __tablename__ = "scope_change_requests"
    __table_args__ = (
        Index("ix_scope_changes_project_status", "org_id", "workspace_id", "project_id", "status"),
        CheckConstraint("status IN ('pending_approval','approved','rejected')", name="ck_scope_change_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    impact_summary: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    estimated_hours_delta: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    budget_delta_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    contract_value_delta_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    schedule_days_delta: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending_approval", server_default="pending_approval")
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    decided_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    approval_id: Mapped[str | None] = mapped_column(ForeignKey("approvals.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TimeEntry(Base):
    __tablename__ = "time_entries"
    __table_args__ = (
        Index("ix_time_entries_project_date", "org_id", "workspace_id", "project_id", "started_at"),
        CheckConstraint("duration_minutes > 0 AND duration_minutes <= 1440", name="ck_time_entry_duration"),
        CheckConstraint("hourly_cost_minor >= 0", name="ck_time_entry_cost_rate"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    billable: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False)
    hourly_cost_minor: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class ProjectCost(Base):
    __tablename__ = "project_costs"
    __table_args__ = (
        Index("ix_project_costs_project_date", "org_id", "workspace_id", "project_id", "incurred_at"),
        CheckConstraint("amount_minor >= 0", name="ck_project_cost_nonnegative"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    incurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
