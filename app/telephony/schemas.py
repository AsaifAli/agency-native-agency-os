from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class CallCreate(BaseModel):
    workspace_id: str
    direction: str = Field(pattern="^(inbound|outbound)$")
    phone_number: str = Field(min_length=5, max_length=50)
    lead_id: str | None = None
    contact_id: str | None = None
    purpose: str = Field(default="", max_length=240)
    recording_consent: str = Field(default="not_requested", pattern="^(not_requested|pending|granted|declined)$")


class CallStatusUpdate(BaseModel):
    status: str = Field(pattern="^(queued|ringing|in_progress|completed|failed|cancelled)$")
    outcome: str = Field(default="", max_length=80)
    summary: str = Field(default="", max_length=12000)
    duration_seconds: int | None = Field(default=None, ge=0, le=86400)
    provider: str | None = Field(default=None, max_length=80)
    provider_call_id: str | None = Field(default=None, max_length=200)


class TranscriptCreate(BaseModel):
    transcript_text: str = Field(min_length=1, max_length=200000)
    language: str = Field(default="und", max_length=24)
    source: str = Field(default="manual", pattern="^(manual|provider|speech_to_text)$")


class CallOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workspace_id: str
    lead_id: str | None
    contact_id: str | None
    direction: str
    status: str
    provider: str
    provider_call_id: str | None
    phone_number: str
    purpose: str
    outcome: str
    summary: str
    recording_consent: str
    duration_seconds: int | None
    started_at: datetime | None
    ended_at: datetime | None
    created_at: datetime


class TranscriptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    call_id: str
    transcript_text: str
    language: str
    source: str
    redaction_status: str
    created_at: datetime
