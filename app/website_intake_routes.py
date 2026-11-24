"""Authenticated-by-signature intake for the public agency website.

The request cannot choose its organization or workspace. Those are pinned in
server configuration. No outreach or external side effect is started here.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from app.audit import record_event
from app.config import settings
from app.db import get_db
from app.domain_models import Contact, Lead
from app.models import FounderAuthority, Workspace
from app.telephony.models import OutboxEvent

router = APIRouter(tags=["website-intake"])
MAX_BODY_BYTES = 16_000
EMAIL_PATTERN = r"^[^\s@]+@[^\s@]+\.[^\s@]+$"


class WebsiteLeadEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    submission_id: str = Field(min_length=16, max_length=160, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=320, pattern=EMAIL_PATTERN)
    company: str = Field(default="", max_length=160)
    project_type: str = Field(min_length=2, max_length=100)
    budget_range: str = Field(default="", max_length=80)
    timeline: str = Field(default="", max_length=80)
    source: str = Field(default="agency_website", pattern=r"^agency_website$")
    submitted_at: datetime


def _header(request: Request, name: str) -> str:
    return (request.headers.get(name) or "").strip()


@router.post("/v1/integrations/website-leads", status_code=202)
async def receive_website_lead(request: Request, db: Session = Depends(get_db)):
    if not settings.website_lead_intake_enabled:
        raise HTTPException(404, "Not found")
    secret = settings.website_lead_intake_secret or ""
    key_id = settings.website_lead_intake_key_id
    org_id = settings.website_lead_intake_org_id
    workspace_id = settings.website_lead_intake_workspace_id
    if not all((secret, key_id, org_id, workspace_id)) or len(secret) < 32:
        raise HTTPException(503, "Website intake is not fully configured")

    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_BODY_BYTES:
            raise HTTPException(413, "Invalid website lead payload size")
        chunks.append(chunk)
    raw = b"".join(chunks)
    if not raw:
        raise HTTPException(400, "Empty website lead payload")

    timestamp = _header(request, "X-AgencyOS-Timestamp")
    supplied_key_id = _header(request, "X-AgencyOS-Key-Id")
    signature = _header(request, "X-AgencyOS-Signature")
    idempotency_key = _header(request, "Idempotency-Key")
    if not timestamp.isdigit() or not re.fullmatch(r"[a-f0-9]{64}", signature):
        raise HTTPException(401, "Invalid integration authentication")
    if not hmac.compare_digest(supplied_key_id, key_id):
        raise HTTPException(401, "Invalid integration authentication")
    if abs(int(time.time()) - int(timestamp)) > settings.website_lead_intake_clock_skew_seconds:
        raise HTTPException(401, "Expired integration request")
    expected = hmac.new(secret.encode(), timestamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(401, "Invalid integration authentication")

    try:
        payload = WebsiteLeadEnvelope.model_validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(422, "Invalid website lead envelope") from exc
    if not idempotency_key or not hmac.compare_digest(idempotency_key, payload.submission_id):
        raise HTTPException(400, "Idempotency key does not match submission")

    workspace = db.query(Workspace).filter_by(id=workspace_id, org_id=org_id).first()
    if workspace is None:
        raise HTTPException(503, "Configured website intake workspace is unavailable")
    founder = db.query(FounderAuthority).filter_by(org_id=org_id, active=True).first()
    if founder is None:
        raise HTTPException(503, "Founder authority is not provisioned")

    existing = db.query(Lead).filter_by(
        org_id=org_id, workspace_id=workspace_id,
        source=payload.source, external_key=payload.submission_id,
    ).one_or_none()
    if existing is not None:
        return {"accepted": True, "lead_id": existing.id, "duplicate": True}

    name_parts = payload.name.split(" ", 1)
    contact = db.query(Contact).filter(
        Contact.org_id == org_id,
        Contact.workspace_id == workspace_id,
        Contact.email == payload.email.lower(),
    ).first()
    try:
        if contact is None:
            contact = Contact(
                org_id=org_id, workspace_id=workspace_id,
                first_name=name_parts[0], last_name=name_parts[1] if len(name_parts) > 1 else "",
                email=payload.email.lower(), source=payload.source,
                consent_status="unknown", created_by=founder.user_id,
            )
            db.add(contact)
            db.flush()

        notes = "Website enquiry. " + "; ".join(
            value for value in (
                f"Project type: {payload.project_type}",
                f"Budget range: {payload.budget_range}" if payload.budget_range else "",
                f"Timeline: {payload.timeline}" if payload.timeline else "",
            ) if value
        )
        lead = Lead(
            org_id=org_id, workspace_id=workspace_id, contact_id=contact.id,
            company_name=payload.company or payload.name, contact_name=payload.name,
            email=payload.email.lower(), source=payload.source,
            external_key=payload.submission_id, score=0,
            qualification_notes=notes, created_by=founder.user_id,
        )
        db.add(lead)
        db.flush()
        record_event(
            db, org_id, None, "lead.received_from_website", "lead", lead.id,
            workspace_id, {"source": payload.source, "submission_id": payload.submission_id},
        )
        db.add(OutboxEvent(
            org_id=org_id, workspace_id=workspace_id,
            event_type="revenue.website_lead_received", schema_version=1,
            aggregate_type="lead", aggregate_id=lead.id,
            idempotency_key=f"website-lead:{payload.submission_id}",
            payload={"lead_id": lead.id, "source": payload.source, "submission_id": payload.submission_id},
            status="pending", attempts=0, max_attempts=8,
            available_at=datetime.now(timezone.utc),
        ))
        db.commit()
        return {"accepted": True, "lead_id": lead.id, "duplicate": False}
    except Exception:
        db.rollback()
        duplicate = db.query(Lead).filter_by(
            org_id=org_id, workspace_id=workspace_id,
            source=payload.source, external_key=payload.submission_id,
        ).one_or_none()
        if duplicate is not None:
            return {"accepted": True, "lead_id": duplicate.id, "duplicate": True}
        raise
