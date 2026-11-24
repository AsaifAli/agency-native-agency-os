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
    review_required: bool = True


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
    created_at: datetime
