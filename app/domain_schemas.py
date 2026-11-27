"""Validated API contracts for Revenue and Delivery resources."""
from datetime import datetime
from decimal import Decimal
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
    phone_call_consent_status: str = Field(default="unknown", pattern="^(unknown|pending|granted|withdrawn)$")
    phone_call_consent_source: str = Field(default="", max_length=200)
    phone_call_consent_recorded_at: datetime | None = None


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
    phone_call_consent_status: str
    phone_call_consent_source: str
    phone_call_consent_recorded_at: datetime | None
    created_at: datetime


class ContactActivityCreate(BaseModel):
    workspace_id: str
    contact_id: str
    activity_type: str = Field(pattern="^(note|call|email|meeting|task|status_update)$")
    direction: str = Field(default="none", pattern="^(none|inbound|outbound|internal)$")
    subject: str = Field(default="", max_length=240)
    body: str = Field(default="", max_length=4000)
    outcome: str = Field(default="", max_length=240)
    source_reference: str = Field(default="", max_length=200)
    occurred_at: datetime | None = None


class ContactActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workspace_id: str
    contact_id: str
    activity_type: str
    direction: str
    subject: str
    body: str
    outcome: str
    source_reference: str
    occurred_at: datetime
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


class LeadResearchSource(BaseModel):
    label: str = Field(min_length=2, max_length=240)
    url: str = Field(min_length=8, max_length=2000)
    accessed_at: datetime
    published_at: datetime | None = None


class LeadResearchCreate(BaseModel):
    workspace_id: str
    lead_id: str
    summary: str = Field(min_length=20, max_length=12000)
    fit_score: int = Field(ge=0, le=100)
    confidence_score: int = Field(ge=0, le=100)
    buying_signals: list[str] = Field(default_factory=list, max_length=50)
    risks: list[str] = Field(default_factory=list, max_length=50)
    source_references: list[LeadResearchSource] = Field(min_length=1, max_length=30)
    researched_at: datetime | None = None


class LeadResearchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workspace_id: str
    lead_id: str
    summary: str
    fit_score: int
    confidence_score: int
    buying_signals: list
    risks: list
    source_references: list
    researched_at: datetime
    created_by: str
    created_at: datetime


class OutreachDraftCreate(BaseModel):
    workspace_id: str
    lead_id: str
    contact_id: str | None = None
    channel: str = Field(pattern="^(email|linkedin|call_script)$")
    subject: str = Field(default="", max_length=240)
    body: str = Field(min_length=20, max_length=12000)
    personalization_basis: str = Field(default="", max_length=6000)
    source_research_ids: list[str] = Field(default_factory=list, max_length=30)


class OutreachDraftReview(BaseModel):
    decision: str = Field(pattern="^(approve_draft|reject)$")
    note: str = Field(default="", max_length=2000)


class OutreachDraftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workspace_id: str
    lead_id: str
    contact_id: str | None
    channel: str
    subject: str
    body: str
    personalization_basis: str
    source_research_ids: list
    status: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    review_note: str
    created_by: str
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
    client_id: str | None = None


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
    contract_value_minor: int = Field(default=0, ge=0)
    estimated_hours: int = Field(default=0, ge=0, le=100000)
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
    contract_value_minor: int
    estimated_hours: int
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


class ProjectOutcomeCreate(BaseModel):
    workspace_id: str
    title: str = Field(min_length=3, max_length=240)
    problem_statement: str = Field(min_length=10, max_length=10000)
    desired_outcome: str = Field(min_length=10, max_length=10000)
    metric_name: str = Field(min_length=2, max_length=160)
    metric_unit: str = Field(min_length=1, max_length=64)
    direction: str = Field(pattern="^(increase|decrease)$")
    baseline_value: Decimal | None = Field(default=None, max_digits=20, decimal_places=6)
    target_value: Decimal = Field(max_digits=20, decimal_places=6)
    target_date: datetime | None = None
    measurement_method: str = Field(min_length=10, max_length=10000)
    acceptance_criteria: list[str] = Field(min_length=1, max_length=20)


class ProjectOutcomeOut(BaseModel):
    id: str
    workspace_id: str
    project_id: str
    title: str
    problem_statement: str
    desired_outcome: str
    metric_name: str
    metric_unit: str
    direction: str
    baseline_value: Decimal | None
    target_value: Decimal
    target_date: datetime | None
    measurement_method: str
    acceptance_criteria: list[str]
    delivery_acceptance_status: str
    acceptance_results: dict[str, bool]
    acceptance_note: str
    accepted_by_user_id: str | None
    accepted_at: datetime | None
    latest_value: Decimal | None
    latest_measured_at: datetime | None
    measurement_count: int
    impact_status: str
    created_at: datetime


class OutcomeMeasurementCreate(BaseModel):
    workspace_id: str
    value: Decimal = Field(max_digits=20, decimal_places=6)
    measured_at: datetime | None = None
    source_type: str = Field(pattern="^(agency_measured|client_reported|system_measured|independently_verified)$")
    source_reference: str = Field(min_length=2, max_length=240)
    evidence_summary: str = Field(min_length=10, max_length=10000)
    supporting_evaluation_run_id: str | None = None
    milestone_id: str | None = None


class OutcomeMeasurementOut(BaseModel):
    id: str
    workspace_id: str
    outcome_id: str
    value: Decimal
    measured_at: datetime
    source_type: str
    source_reference: str
    evidence_summary: str
    supporting_evaluation_run_id: str | None
    milestone_id: str | None
    created_at: datetime


class OutcomeAcceptanceDecision(BaseModel):
    workspace_id: str
    decision: str = Field(pattern="^(accepted|rejected)$")
    criteria_results: dict[str, bool]
    note: str = Field(min_length=10, max_length=5000)
