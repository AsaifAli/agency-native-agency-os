"""Workforce and delegation API contracts."""
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


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
