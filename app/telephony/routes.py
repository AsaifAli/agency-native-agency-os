"""Authenticated, workspace-scoped telephony record APIs.

These endpoints record call intent and provider results. They do not place calls;
a provider adapter and approval/consent enforcement must be configured separately.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.auth import get_principal, require_membership, require_role, Principal
from app.db import get_db
from app.models import Role
from app.domain_models import Lead, Contact
from app.audit import record_event
from app.telephony.models import CallSession, CallTranscript, OutboxEvent
from app.telephony.schemas import CallCreate, CallStatusUpdate, CallOut, TranscriptCreate, TranscriptOut

router = APIRouter(prefix="/v1/orgs/{org_id}/telephony", tags=["telephony"])
WRITERS = {Role.owner, Role.admin, Role.operator}


def _scope(db: Session, org_id: str, workspace_id: str):
    from app.models import Workspace
    if not db.query(Workspace.id).filter_by(id=workspace_id, org_id=org_id).first():
        raise HTTPException(404, "Workspace not found")


def _write(db: Session, org_id: str, workspace_id: str, principal: Principal):
    role = require_membership(org_id, principal, db)
    require_role(role, WRITERS)
    _scope(db, org_id, workspace_id)


def _call(db: Session, org_id: str, call_id: str):
    item = db.query(CallSession).filter_by(id=call_id, org_id=org_id).first()
    if item is None:
        raise HTTPException(404, "Call not found")
    return item


def _outbox(db, org_id, workspace_id, event_type, aggregate_id, payload, key_suffix="created"):
    db.add(OutboxEvent(
        org_id=org_id, workspace_id=workspace_id, event_type=event_type,
        schema_version=1, aggregate_type="call", aggregate_id=aggregate_id,
        idempotency_key=f"{event_type}:{aggregate_id}:{key_suffix}", payload=payload,
    ))


@router.get("/calls", response_model=list[CallOut])
def list_calls(org_id: str, workspace_id: str = Query(min_length=1),
               lead_id: str | None = None, limit: int = Query(default=100, ge=1, le=500),
               db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    require_membership(org_id, p, db)
    _scope(db, org_id, workspace_id)
    q = db.query(CallSession).filter_by(org_id=org_id, workspace_id=workspace_id)
    if lead_id:
        q = q.filter_by(lead_id=lead_id)
    return q.order_by(CallSession.created_at.desc()).limit(limit).all()


@router.post("/calls", response_model=CallOut, status_code=201)
def create_call(org_id: str, body: CallCreate,
                db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    _write(db, org_id, body.workspace_id, p)
    if body.lead_id and not db.query(Lead.id).filter_by(
        id=body.lead_id, org_id=org_id, workspace_id=body.workspace_id
    ).first():
        raise HTTPException(404, "Lead not found")
    if body.contact_id and not db.query(Contact.id).filter_by(
        id=body.contact_id, org_id=org_id, workspace_id=body.workspace_id
    ).first():
        raise HTTPException(404, "Contact not found")
    item = CallSession(
        org_id=org_id, workspace_id=body.workspace_id, lead_id=body.lead_id,
        contact_id=body.contact_id, direction=body.direction,
        status="planned" if body.direction == "outbound" else "queued",
        phone_number=body.phone_number.strip(), purpose=body.purpose,
        recording_consent=body.recording_consent, created_by=p.user.id,
    )
    db.add(item)
    db.flush()
    _outbox(db, org_id, body.workspace_id, "telephony.call_recorded", item.id,
            {"direction": item.direction, "status": item.status, "lead_id": item.lead_id})
    record_event(db, org_id, p.user.id, "telephony.call_created", "call", item.id,
                 body.workspace_id, {"direction": item.direction, "status": item.status})
    db.commit()
    db.refresh(item)
    return item


@router.patch("/calls/{call_id}", response_model=CallOut)
def update_call(org_id: str, call_id: str, body: CallStatusUpdate,
                db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    item = _call(db, org_id, call_id)
    _write(db, org_id, item.workspace_id, p)
    if item.status in {"completed", "failed", "cancelled"}:
        raise HTTPException(409, "Terminal call records cannot be changed")
    allowed_transitions = {
        "planned": {"queued", "cancelled", "failed"},
        "queued": {"ringing", "in_progress", "failed", "cancelled"},
        "ringing": {"in_progress", "failed", "cancelled"},
        "in_progress": {"completed", "failed", "cancelled"},
    }
    if body.status not in allowed_transitions.get(item.status, set()):
        raise HTTPException(409, f"Invalid call status transition: {item.status} -> {body.status}")
    # Outbound calls require an explicitly consented CRM contact; a lead alone is not permission.
    if item.direction == "outbound" and body.status == "queued":
        if not item.contact_id:
            raise HTTPException(403, "Outbound call requires a linked contact with explicit call consent")
        contact = db.query(Contact).filter_by(id=item.contact_id, org_id=org_id, workspace_id=item.workspace_id).first()
        if contact is None or contact.consent_status != "granted":
            raise HTTPException(403, "Outbound call blocked: contact call consent is not granted")
        if item.lead_id:
            lead = db.query(Lead).filter_by(id=item.lead_id, org_id=org_id, workspace_id=item.workspace_id).first()
            if lead is None or lead.stage == "suppressed" or lead.suppression_reason:
                raise HTTPException(403, "Outbound call blocked: lead is suppressed or unavailable")
    if body.provider_call_id and not body.provider:
        raise HTTPException(422, "Provider name is required with provider_call_id")
    if body.provider_call_id and body.provider and db.query(CallSession.id).filter(
        CallSession.provider == body.provider,
        CallSession.provider_call_id == body.provider_call_id,
        CallSession.id != item.id,
    ).first():
        raise HTTPException(409, "Provider call ID already belongs to another call")
    now = datetime.now(timezone.utc)
    item.status = body.status
    item.outcome = body.outcome
    item.summary = body.summary
    item.duration_seconds = body.duration_seconds
    if body.provider:
        item.provider = body.provider
    if body.provider_call_id:
        item.provider_call_id = body.provider_call_id
    if body.status == "in_progress" and item.started_at is None:
        item.started_at = now
    if body.status in {"completed", "failed", "cancelled"}:
        item.ended_at = now
    db.flush()
    _outbox(db, org_id, item.workspace_id, "telephony.call_status_changed", item.id,
            {"status": item.status, "outcome": item.outcome}, key_suffix=body.status)
    record_event(db, org_id, p.user.id, "telephony.call_updated", "call", item.id,
                 item.workspace_id, {"status": item.status})
    db.commit()
    db.refresh(item)
    return item


@router.post("/calls/{call_id}/transcripts", response_model=TranscriptOut, status_code=201)
def add_transcript(org_id: str, call_id: str, body: TranscriptCreate,
                   db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    item = _call(db, org_id, call_id)
    _write(db, org_id, item.workspace_id, p)
    transcript = CallTranscript(
        org_id=org_id, workspace_id=item.workspace_id, call_id=item.id,
        transcript_text=body.transcript_text, language=body.language,
        source=body.source,
    )
    db.add(transcript)
    db.flush()
    _outbox(db, org_id, item.workspace_id, "telephony.transcript_added", item.id,
            {"transcript_id": transcript.id, "language": transcript.language}, key_suffix=transcript.id)
    record_event(db, org_id, p.user.id, "telephony.transcript_added", "call", item.id,
                 item.workspace_id, {"transcript_id": transcript.id})
    db.commit()
    db.refresh(transcript)
    return transcript


@router.get("/calls/{call_id}/transcripts", response_model=list[TranscriptOut])
def list_transcripts(org_id: str, call_id: str,
                     db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    item = _call(db, org_id, call_id)
    require_membership(org_id, p, db)
    _scope(db, org_id, item.workspace_id)
    return db.query(CallTranscript).filter_by(
        org_id=org_id, workspace_id=item.workspace_id, call_id=item.id
    ).order_by(CallTranscript.created_at.asc()).all()
