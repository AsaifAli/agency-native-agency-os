from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class SenderCreate(BaseModel):
    workspace_id: str
    display_name: str = Field(min_length=2, max_length=160)
    email_address: str = Field(pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$", max_length=320)
    max_per_hour: int = Field(default=10, ge=1, le=100)
    max_per_day: int = Field(default=50, ge=1, le=1000)


class SenderStatusUpdate(BaseModel):
    status: str = Field(pattern="^(active|paused)$")


class ConsentCreate(BaseModel):
    workspace_id: str
    contact_id: str
    channel: str = Field(pattern="^(email|phone|sms)$")
    status: str = Field(pattern="^(unknown|granted|legitimate_interest_reviewed|withdrawn)$")
    legal_basis: str = Field(pattern="^(consent|legitimate_interest|contractual|other)$")
    source: str = Field(min_length=2, max_length=160)
    evidence_reference: str = Field(default="", max_length=240)
    review_note: str = Field(default="", max_length=2000)
    recorded_at: datetime | None = None


class MessageCreate(BaseModel):
    workspace_id: str
    sender_id: str
    contact_id: str
    lead_id: str | None = None
    subject: str = Field(min_length=2, max_length=240)
    body: str = Field(min_length=10, max_length=20000)
    purpose: str = Field(default="", max_length=240)


class StopEventCreate(BaseModel):
    event_type: str = Field(pattern="^(reply|opt_out|bounce|delivered|failed)$")
    source: str = Field(default="manual", pattern="^(manual|provider)$")
    external_event_id: str | None = Field(default=None, max_length=240)
    occurred_at: datetime | None = None
    note: str = Field(default="", max_length=2000)


class BlockRelease(BaseModel):
    note: str = Field(min_length=3, max_length=2000)


class SenderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workspace_id: str
    display_name: str
    email_address: str
    status: str
    max_per_hour: int
    max_per_day: int
    approved_by: str | None
    approved_at: datetime | None
    created_at: datetime


class ConsentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workspace_id: str
    contact_id: str
    channel: str
    status: str
    legal_basis: str
    source: str
    evidence_reference: str
    review_note: str
    recorded_at: datetime
    recorded_by: str


class BlockOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workspace_id: str
    contact_id: str
    channel: str
    status: str
    reason: str
    source: str
    note: str
    recorded_at: datetime
    released_by: str | None
    released_at: datetime | None
    release_note: str


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workspace_id: str
    sender_id: str
    contact_id: str
    lead_id: str | None
    channel: str
    recipient: str
    subject: str
    body: str
    purpose: str
    status: str
    consent_id: str | None
    approval_id: str | None
    queued_at: datetime | None
    provider_message_id: str | None
    sent_at: datetime | None
    stop_reason: str
    created_by: str
    created_at: datetime


class MessageEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    message_id: str
    event_type: str
    source: str
    external_event_id: str | None
    occurred_at: datetime
    payload: dict
    recorded_by: str
    created_at: datetime
