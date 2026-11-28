from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from app.models import DataClass, Role, ApprovalStatus, ExecutionStatus

class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
class WorkspaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    org_id: str
    name: str
    created_at: datetime

class AgentCreate(BaseModel):
    workspace_id: str
    name: str = Field(min_length=2, max_length=200)
    department: str = "Engineering"
    instructions: str = ""
    runtime: str = "claude_managed_agents"
    data_class: DataClass = DataClass.synthetic
class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workspace_id: str
    name: str
    department: str
    runtime: str
    data_class: DataClass
    enabled: bool

class TaskCreate(BaseModel):
    workspace_id: str
    title: str = Field(min_length=2, max_length=300)
    description: str = ""
    milestone_id: str | None = None
class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workspace_id: str
    milestone_id: str | None = None
    title: str
    description: str
    status: str
    created_at: datetime

class ApprovalDecision(BaseModel):
    decision: ApprovalStatus
    note: str = ""
class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    event_type: str
    resource_type: str
    resource_id: str
    payload: dict
    created_at: datetime

class ApprovalCreate(BaseModel):
    workspace_id: str
    action_type: str = Field(min_length=3, max_length=100)
    resource_id: str = Field(min_length=1, max_length=36)
    idempotency_key: str = Field(min_length=8, max_length=160)
    request_payload: dict = Field(default_factory=dict)

class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workspace_id: str
    action_type: str
    resource_id: str
    status: ApprovalStatus
    request_payload: dict
    requested_by: str
    decision_note: str
    created_at: datetime
    consumed_at: datetime | None = None


class EvaluationCreate(BaseModel):
    workspace_id: str
    pack_name: str = Field(min_length=2, max_length=100)
    expected: dict = Field(default_factory=dict)
    actual: dict = Field(default_factory=dict)
    task_id: str | None = None

class EvaluationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workspace_id: str
    task_id: str | None
    pack_name: str
    score: float
    passed: bool
    metrics: dict
    gate_results: dict
    evidence_trust: str = "self_reported"
    release_eligible: bool = False
    created_at: datetime


class ExecutionCreate(BaseModel):
    workspace_id: str
    task_id: str
    agent_id: str
    idempotency_key: str = Field(min_length=8, max_length=160)
    max_attempts: int = Field(default=3, ge=1, le=10)


class ExecutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    task_id: str
    agent_id: str
    runtime: str
    data_class: DataClass
    status: ExecutionStatus
    attempt_count: int
    max_attempts: int
    error_code: str | None
    error_message: str | None
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime
    provider_usage: dict | None = None
