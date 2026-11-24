"""Workforce and delegation API contracts."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class WorkforceInit(BaseModel):
    workspace_id: str


class WorkforceCapabilityCreate(BaseModel):
    capability_key: str = Field(min_length=3, max_length=120)
    scope: str = Field(default="workspace", pattern="^(self|team|workspace)$")
    allowed_data_classes: list[str] = Field(default_factory=lambda: ["synthetic"], max_length=5)
    allowed_actions: list[str] = Field(default_factory=list, max_length=50)
    tool_allowlist: list[str] = Field(default_factory=list, max_length=50)
    budget_minor: int = Field(default=0, ge=0, le=2_000_000_000)
    currency: str = Field(default="INR", pattern="^[A-Z]{3}$")


class WorkforceMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    unit_id: str | None
    manager_member_id: str | None
    agent_id: str | None
    member_type: str
    name: str
    title: str
    department_key: str
    responsibilities: list
    autonomy_level: int
    status: str
    is_founder_reserved: bool
    created_at: datetime
    updated_at: datetime


class WorkforceUnitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    parent_unit_id: str | None
    name: str
    unit_type: str
    department_key: str
    description: str


class WorkforceCapabilityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    member_id: str
    capability_key: str
    scope: str
    allowed_data_classes: list
    allowed_actions: list
    tool_allowlist: list
    budget_minor: int
    currency: str
    enabled: bool


class DelegationCreate(BaseModel):
    workspace_id: str
    parent_task_id: str
    child_title: str = Field(min_length=2, max_length=300)
    child_description: str = Field(default="", max_length=12000)
    delegated_by_member_id: str
    assigned_to_member_id: str
    dependency_task_id: str | None = None
    depends_on_ordinal: int | None = Field(default=None, ge=1, le=50)
    review_required: bool = True
    sequence_no: int = Field(default=1, ge=1, le=10000)


class DelegationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workspace_id: str
    parent_task_id: str
    child_task_id: str
    delegated_by_member_id: str
    assigned_to_member_id: str
    dependency_task_id: str | None
    review_required: bool
    review_status: str
    status: str
    sequence_no: int
    last_error_code: str | None
    created_at: datetime
    updated_at: datetime


class OrchestrationPlanCreate(BaseModel):
    workspace_id: str
    objective: str = Field(min_length=5, max_length=2000)
    created_by_member_id: str
    plan_title: str = Field(default="Agency work plan", min_length=2, max_length=200)
    tasks: list[DelegationCreate] = Field(min_length=1, max_length=50)


class OrchestrationPlanOut(BaseModel):
    id: str
    objective: str
    status: str
    task_count: int
    ready_count: int
    blocked_count: int
    awaiting_review_count: int
    failed_count: int
    succeeded_count: int
    created_at: datetime
    updated_at: datetime


DepartmentKey = Literal[
    "marketing_brand",
    "business_development_sales",
    "market_research_intelligence",
    "solutions_consulting_strategy",
    "finance_accounts",
    "legal_risk_compliance",
    "ai_research_innovation",
    "ai_engineering_development",
    "automation_integration_engineering",
    "infrastructure_it_operations",
    "pmo",
    "delivery_implementation",
    "quality_assurance_security",
    "client_success_support",
    "hr_people_operations",
    "administration_procurement",
]


class SuggestedPlanTask(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(min_length=5, max_length=900)
    department_key: DepartmentKey
    depends_on_ordinal: int | None = Field(default=None, ge=1, le=10)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=4)
    review_required: Literal[True] = True


class SuggestedPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    schema_version: Literal[1] = 1
    summary: str = Field(min_length=5, max_length=600)
    tasks: list[SuggestedPlanTask] = Field(min_length=1, max_length=10)
    risks: list[str] = Field(default_factory=list, max_length=5)
    founder_decisions: list[str] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def validate_dependency_ordinals(self):
        for ordinal, task in enumerate(self.tasks, start=1):
            dependency = task.depends_on_ordinal
            if dependency is not None and dependency >= ordinal:
                raise ValueError("Dependencies must reference earlier task ordinals")
        return self


class PlanDraftCreate(BaseModel):
    workspace_id: str
    objective: str = Field(min_length=5, max_length=2000)
    plan_title: str = Field(default="Chief of Staff proposal", min_length=2, max_length=200)
    idempotency_key: str = Field(min_length=16, max_length=160, pattern="^[A-Za-z0-9_-]+$")


class PlanDraftAssignment(BaseModel):
    ordinal: int = Field(ge=1, le=10)
    delegated_by_member_id: str
    assigned_to_member_id: str
    review_required: bool = True


class PlanDraftApprove(BaseModel):
    assignments: list[PlanDraftAssignment] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def validate_unique_ordinals(self):
        ordinals = [item.ordinal for item in self.assignments]
        if len(ordinals) != len(set(ordinals)):
            raise ValueError("Each suggested task can only be assigned once")
        return self


class PlanDraftReject(BaseModel):
    reason: str = Field(default="", max_length=300)


class PlanDraftOut(BaseModel):
    id: str
    workspace_id: str
    execution_id: str
    objective: str
    plan_title: str
    status: str
    suggested_plan: dict
    error_code: str | None
    approved_plan_id: str | None
    created_at: datetime
    updated_at: datetime

