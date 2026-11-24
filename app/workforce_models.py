"""Governed agency workforce registry and explicit delegation lineage."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON,
    String, Text, UniqueConstraint, false,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class WorkforceUnit(Base):
    __tablename__ = "workforce_units"
    __table_args__ = (
        CheckConstraint("unit_type IN ('office','group','department','team')", name="ck_workforce_unit_type"),
        UniqueConstraint("org_id", "workspace_id", "department_key", "name", name="uq_workforce_unit_name"),
        Index("ix_workforce_unit_scope_parent", "org_id", "workspace_id", "parent_unit_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    parent_unit_id: Mapped[str | None] = mapped_column(ForeignKey("workforce_units.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    unit_type: Mapped[str] = mapped_column(String(24), nullable=False)
    department_key: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class WorkforceMember(Base):
    __tablename__ = "workforce_members"
    __table_args__ = (
        CheckConstraint("member_type IN ('human','agent','supervisor','sub_agent')", name="ck_workforce_member_type"),
        CheckConstraint("autonomy_level BETWEEN 0 AND 3", name="ck_workforce_autonomy_level"),
        CheckConstraint("status IN ('planned','active','paused','retired')", name="ck_workforce_member_status"),
        UniqueConstraint("org_id", "workspace_id", "name", "title", name="uq_workforce_member_name_title"),
        Index("ix_workforce_member_scope_manager", "org_id", "workspace_id", "manager_member_id"),
        Index("ix_workforce_member_scope_unit", "org_id", "workspace_id", "unit_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    unit_id: Mapped[str | None] = mapped_column(ForeignKey("workforce_units.id", ondelete="CASCADE"))
    manager_member_id: Mapped[str | None] = mapped_column(ForeignKey("workforce_members.id", ondelete="RESTRICT"))
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"))
    member_type: Mapped[str] = mapped_column(String(24), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    department_key: Mapped[str] = mapped_column(String(80), nullable=False)
    responsibilities: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    autonomy_level: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="planned", server_default="planned", nullable=False)
    is_founder_reserved: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class WorkforceCapability(Base):
    __tablename__ = "workforce_capabilities"
    __table_args__ = (
        CheckConstraint("scope IN ('self','team','workspace')", name="ck_workforce_capability_scope"),
        CheckConstraint("budget_minor >= 0", name="ck_workforce_capability_budget"),
        UniqueConstraint("member_id", "capability_key", name="uq_workforce_member_capability"),
        Index("ix_workforce_capability_scope", "org_id", "workspace_id", "member_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    member_id: Mapped[str] = mapped_column(ForeignKey("workforce_members.id", ondelete="CASCADE"), nullable=False)
    capability_key: Mapped[str] = mapped_column(String(120), nullable=False)
    scope: Mapped[str] = mapped_column(String(24), default="workspace", server_default="workspace", nullable=False)
    allowed_data_classes: Mapped[list] = mapped_column(JSON, default=lambda: ["synthetic"], nullable=False)
    allowed_actions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    tool_allowlist: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    budget_minor: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", server_default="INR", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class Delegation(Base):
    __tablename__ = "delegations"
    __table_args__ = (
        CheckConstraint("parent_task_id <> child_task_id", name="ck_delegation_non_self"),
        CheckConstraint("review_status IN ('pending','approved','changes_requested','waived')", name="ck_delegation_review_status"),
        CheckConstraint("status IN ('blocked','ready','queued','running','awaiting_review','succeeded','failed','cancelled')", name="ck_delegation_status"),
        UniqueConstraint("parent_task_id", "child_task_id", name="uq_delegation_parent_child"),
        Index("ix_delegation_scope_parent", "org_id", "workspace_id", "parent_task_id"),
        Index("ix_delegation_scope_assignee", "org_id", "workspace_id", "assigned_to_member_id"),
        Index("ix_delegation_scope_status", "org_id", "workspace_id", "status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    parent_task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    child_task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    delegated_by_member_id: Mapped[str] = mapped_column(ForeignKey("workforce_members.id", ondelete="RESTRICT"), nullable=False)
    assigned_to_member_id: Mapped[str] = mapped_column(ForeignKey("workforce_members.id", ondelete="RESTRICT"), nullable=False)
    dependency_task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"))
    review_required: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False)
    review_status: Mapped[str] = mapped_column(String(24), default="pending", server_default="pending", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="ready", server_default="ready", nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    last_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class OrchestrationPlan(Base):
    """Persisted supervisor plan; OS owns the plan and task graph."""
    __tablename__ = "orchestration_plans"
    __table_args__ = (
        CheckConstraint("status IN ('planned','in_progress','awaiting_review','succeeded','failed','cancelled')", name="ck_orchestration_plan_status"),
        Index("ix_orchestration_plan_scope_status", "org_id", "workspace_id", "status"),
        Index("ix_orchestration_plan_root_task", "root_task_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    root_task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    created_by_member_id: Mapped[str] = mapped_column(ForeignKey("workforce_members.id", ondelete="RESTRICT"), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    plan_title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="planned", server_default="planned", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class OrchestrationPlanDelegation(Base):
    __tablename__ = "orchestration_plan_delegations"
    __table_args__ = (UniqueConstraint("plan_id", "ordinal", name="uq_plan_delegation_ordinal"),)
    plan_id: Mapped[str] = mapped_column(ForeignKey("orchestration_plans.id", ondelete="CASCADE"), primary_key=True)
    delegation_id: Mapped[str] = mapped_column(ForeignKey("delegations.id", ondelete="CASCADE"), primary_key=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)


class WorkforcePosition(Base):
    """Durable role/position catalogue, independent from a person or agent session."""
    __tablename__ = "workforce_positions"
    __table_args__ = (
        CheckConstraint("autonomy_ceiling BETWEEN 0 AND 3", name="ck_workforce_position_autonomy"),
        CheckConstraint("status IN ('planned','active','paused','retired')", name="ck_workforce_position_status"),
        UniqueConstraint("org_id", "workspace_id", "position_key", name="uq_workforce_position_key"),
        Index("ix_workforce_position_scope_department", "org_id", "workspace_id", "department_key"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    unit_id: Mapped[str | None] = mapped_column(ForeignKey("workforce_units.id", ondelete="CASCADE"))
    team_unit_id: Mapped[str | None] = mapped_column(ForeignKey("workforce_units.id", ondelete="SET NULL"))
    assigned_member_id: Mapped[str | None] = mapped_column(ForeignKey("workforce_members.id", ondelete="SET NULL"))
    position_key: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    department_key: Mapped[str] = mapped_column(String(80), nullable=False)
    group_key: Mapped[str] = mapped_column(String(80), nullable=False)
    team_key: Mapped[str] = mapped_column(String(100), nullable=False)
    reports_to_position_key: Mapped[str | None] = mapped_column(String(160))
    responsibilities: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    autonomy_ceiling: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="planned", server_default="planned", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)
