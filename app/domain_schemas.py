"""Validated API contracts for Revenue and Delivery resources."""
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class ClientCreate(BaseModel):
    workspace_id: str
    name: str = Field(min_length=2, max_length=200)
    legal_name: str | None = Field(default=None, max_length=240)
    external_key: str | None = Field(default=None, max_length=120)
    industry: str = Field(default="", max_length=120)
    website: str = Field(default="", max_length=500)
    notes: str = Field(default="", max_length=10000)


class ClientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workspace_id: str
    name: str
    legal_name: str | None
    industry: str
    website: str
    status: str
    created_at: datetime


class ContactCreate(BaseModel):
    workspace_id: str
    client_id: str | None = None
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(default="", max_length=120)
    email: str = Field(default="", max_length=320)
    phone: str = Field(default="", max_length=50)
    job_title: str = Field(default="", max_length=160)
    source: str = Field(default="", max_length=120)
    consent_status: str = Field(default="unknown", pattern="^(unknown|pending|granted|withdrawn)$")


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workspace_id: str
    client_id: str | None
    first_name: str
    last_name: str
    email: str
    phone: str
    job_title: str
    source: str
    consent_status: str
    created_at: datetime


class LeadCreate(BaseModel):
    workspace_id: str
    client_id: str | None = None
    contact_id: str | None = None
    company_name: str = Field(min_length=2, max_length=200)
    contact_name: str = Field(default="", max_length=200)
    email: str = Field(default="", max_length=320)
    source: str = Field(default="", max_length=120)
    score: int = Field(default=0, ge=0, le=100)
    qualification_notes: str = Field(default="", max_length=10000)


class LeadStageUpdate(BaseModel):
    stage: str = Field(pattern="^(new|researching|qualified|unqualified|converted|suppressed)$")
    suppression_reason: str = Field(default="", max_length=240)


class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workspace_id: str
    client_id: str | None
    contact_id: str | None
    company_name: str
    contact_name: str
    email: str
    source: str
    stage: str
    score: int
    qualification_notes: str
    suppression_reason: str
    created_at: datetime


class OpportunityCreate(BaseModel):
    workspace_id: str
    client_id: str | None = None
    lead_id: str | None = None
    title: str = Field(min_length=2, max_length=240)
    amount_minor: int = Field(default=0, ge=0)
    currency: str = Field(default="INR", pattern="^[A-Z]{3}$")
    probability: int = Field(default=0, ge=0, le=100)
    expected_close_date: datetime | None = None


class OpportunityStageUpdate(BaseModel):
    stage: str = Field(pattern="^(qualification|discovery|proposal|negotiation|won|lost)$")


class OpportunityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workspace_id: str
    client_id: str | None
    lead_id: str | None
    title: str
    stage: str
    amount_minor: int
    currency: str
    probability: int
    expected_close_date: datetime | None
    created_at: datetime


class ProjectCreate(BaseModel):
    workspace_id: str
    client_id: str | None = None
    opportunity_id: str | None = None
    name: str = Field(min_length=2, max_length=240)
    description: str = Field(default="", max_length=20000)
    priority: str = Field(default="normal", pattern="^(low|normal|high|critical)$")
    budget_minor: int = Field(default=0, ge=0)
    currency: str = Field(default="INR", pattern="^[A-Z]{3}$")
    start_date: datetime | None = None
    due_date: datetime | None = None


class ProjectStatusUpdate(BaseModel):
    status: str = Field(pattern="^(planned|active|blocked|completed|cancelled|on_hold)$")


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workspace_id: str
    client_id: str | None
    opportunity_id: str | None
    name: str
    description: str
    status: str
    priority: str
    budget_minor: int
    currency: str
    start_date: datetime | None
    due_date: datetime | None
    created_at: datetime


class MilestoneCreate(BaseModel):
    workspace_id: str
    project_id: str
    title: str = Field(min_length=2, max_length=240)
    description: str = Field(default="", max_length=10000)
    due_date: datetime | None = None
    sort_order: int = Field(default=0, ge=0, le=100000)


class MilestoneStatusUpdate(BaseModel):
    status: str = Field(pattern="^(pending|in_progress|blocked|completed|cancelled)$")


class MilestoneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workspace_id: str
    project_id: str
    title: str
    description: str
    status: str
    due_date: datetime | None
    sort_order: int
    created_at: datetime
