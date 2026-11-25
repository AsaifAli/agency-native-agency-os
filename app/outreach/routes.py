"""Founder-governed outbound communication preparation and stop controls.

This module never sends email. It prepares an approved queue for a later provider adapter.
"""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import Principal, get_principal, has_founder_authority, require_founder_authority, require_membership, require_role, require_workspace_access_from_context
from app.db import get_db
from app.models import Role, Workspace, Approval, ApprovalStatus
from app.domain_models import Contact, Lead
from app.audit import record_event
from app.action_policy import require_approved_action
from app.telephony.models import OutboxEvent
from app.outreach.models import OutboundSender, CommunicationConsent, CommunicationBlock, OutboundMessage, OutboundMessageEvent
from app.outreach.schemas import (
    SenderCreate, SenderStatusUpdate, ConsentCreate, MessageCreate, StopEventCreate,
    BlockRelease, MessageReject, SenderOut, ConsentOut, BlockOut, MessageOut, MessageEventOut,
)

router = APIRouter(prefix="/v1/orgs/{org_id}/outreach", tags=["outreach"])
WRITERS = {Role.owner, Role.admin, Role.operator}


def _scope(db: Session, org_id: str, workspace_id: str) -> None:
    require_workspace_access_from_context(org_id, workspace_id, db)


def _read(org_id: str, workspace_id: str, p: Principal, db: Session) -> None:
    role = require_membership(org_id, p, db)
    if role not in {Role.owner, Role.admin, Role.operator, Role.reviewer} and not has_founder_authority(db, org_id, p.user.id):
        require_role(role, {Role.owner, Role.admin, Role.operator, Role.reviewer})
    _scope(db, org_id, workspace_id)


def _write(org_id: str, workspace_id: str, p: Principal, db: Session) -> None:
    role = require_membership(org_id, p, db)
    if role not in WRITERS and not has_founder_authority(db, org_id, p.user.id):
        require_role(role, WRITERS)
    _scope(db, org_id, workspace_id)


def _event(db: Session, org_id: str, actor_id: str, event_type: str,
           resource_type: str, resource_id: str, workspace_id: str, payload: dict | None = None) -> None:
    record_event(db, org_id, actor_id, event_type, resource_type, resource_id, workspace_id, payload or {})


def _outbox(db: Session, org_id: str, workspace_id: str, event_type: str,
            aggregate_type: str, aggregate_id: str, payload: dict, key_suffix: str | None = None) -> None:
    key = f"{event_type}:{aggregate_id}:{key_suffix}" if key_suffix else f"{event_type}:{aggregate_id}"
    db.add(OutboxEvent(
        org_id=org_id, workspace_id=workspace_id, event_type=event_type,
        schema_version=1, aggregate_type=aggregate_type, aggregate_id=aggregate_id,
        idempotency_key=key, payload=payload,
    ))


def _lock_contact(db: Session, org_id: str, workspace_id: str, contact_id: str) -> Contact:
    contact = db.query(Contact).filter_by(
        id=contact_id, org_id=org_id, workspace_id=workspace_id,
    ).with_for_update().first()
    if contact is None:
        raise HTTPException(404, "Contact not found")
    return contact


def _latest_consent(db: Session, org_id: str, workspace_id: str, contact_id: str, channel: str):
    return (db.query(CommunicationConsent)
            .filter_by(org_id=org_id, workspace_id=workspace_id, contact_id=contact_id, channel=channel)
            .order_by(CommunicationConsent.recorded_at.desc(), CommunicationConsent.created_at.desc())
            .first())


def _active_block(db: Session, org_id: str, workspace_id: str, contact_id: str, channel: str):
    return db.query(CommunicationBlock).filter_by(
        org_id=org_id, workspace_id=workspace_id, contact_id=contact_id,
        channel=channel, status="active",
    ).with_for_update().first()


def _validate_message_sendability(db: Session, org_id: str, item: OutboundMessage, sender: OutboundSender):
    if sender.status != "active":
        raise HTTPException(409, "Outbound sender is not founder-approved and active")
    contact = db.query(Contact).filter_by(
        id=item.contact_id, org_id=org_id, workspace_id=item.workspace_id,
    ).first()
    if contact is None or not contact.email:
        raise HTTPException(409, "Contact has no current email address")
    if contact.email.lower().strip() != item.recipient.lower().strip():
        raise HTTPException(409, "Contact email changed; create a new draft to refresh the recipient snapshot")
    consent = _latest_consent(db, org_id, item.workspace_id, item.contact_id, "email")
    if consent is None or (item.consent_id is not None and consent.id != item.consent_id):
        raise HTTPException(403, "Current email consent evidence changed; create a new draft")
    if consent.status not in {"granted", "legitimate_interest_reviewed"}:
        raise HTTPException(403, "Email outreach blocked: current channel consent/basis is not eligible")
    if consent.status == "granted" and consent.legal_basis != "consent":
        raise HTTPException(403, "Granted consent must carry the consent legal-basis record")
    if consent.status == "legitimate_interest_reviewed" and (
        consent.legal_basis != "legitimate_interest" or len(consent.review_note.strip()) < 3
    ):
        raise HTTPException(403, "Reviewed legitimate-interest evidence is incomplete")
    if not consent.source.strip() or not consent.evidence_reference.strip():
        raise HTTPException(403, "Channel consent source and evidence reference are required")
    if _active_block(db, org_id, item.workspace_id, item.contact_id, "email"):
        raise HTTPException(403, "Outbound email blocked by an active reply, opt-out, bounce or manual stop")
    if item.lead_id:
        lead = db.query(Lead).filter_by(
            id=item.lead_id, org_id=org_id, workspace_id=item.workspace_id,
        ).first()
        if lead is None or lead.stage in {"suppressed", "unqualified"} or lead.suppression_reason:
            raise HTTPException(403, "Outbound email blocked: linked lead is suppressed or unavailable")
    return contact, consent


def _check_rate_limits(db: Session, org_id: str, item: OutboundMessage, sender: OutboundSender) -> None:
    now = datetime.now(timezone.utc)
    hourly = db.query(func.count(OutboundMessage.id)).filter(
        OutboundMessage.org_id == org_id,
        OutboundMessage.workspace_id == item.workspace_id,
        OutboundMessage.sender_id == sender.id,
        OutboundMessage.queued_at.isnot(None),
        OutboundMessage.queued_at >= now - timedelta(hours=1),
    ).scalar() or 0
    daily = db.query(func.count(OutboundMessage.id)).filter(
        OutboundMessage.org_id == org_id,
        OutboundMessage.workspace_id == item.workspace_id,
        OutboundMessage.sender_id == sender.id,
        OutboundMessage.queued_at.isnot(None),
        OutboundMessage.queued_at >= now - timedelta(days=1),
    ).scalar() or 0
    if hourly >= sender.max_per_hour or daily >= sender.max_per_day:
        raise HTTPException(429, "Approved sender rate limit reached; queue later or request a reviewed limit change")


@router.get("/senders", response_model=list[SenderOut])
def list_senders(
    org_id: str, workspace_id: str = Query(min_length=1),
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    _read(org_id, workspace_id, p, db)
    return (db.query(OutboundSender).filter_by(org_id=org_id, workspace_id=workspace_id)
            .order_by(OutboundSender.created_at.desc()).limit(100).all())


@router.post("/senders", response_model=SenderOut, status_code=201)
def create_sender(
    org_id: str, body: SenderCreate,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    _write(org_id, body.workspace_id, p, db)
    if len(body.display_name.strip()) < 2:
        raise HTTPException(422, "Sender display name must be non-empty")
    address = body.email_address.lower().strip()
    duplicate = db.query(OutboundSender.id).filter_by(
        org_id=org_id, workspace_id=body.workspace_id, email_address=address,
    ).first()
    if duplicate:
        raise HTTPException(409, "Sender address already exists in this workspace")
    item = OutboundSender(
        org_id=org_id, workspace_id=body.workspace_id,
        display_name=body.display_name.strip(), email_address=address,
        max_per_hour=body.max_per_hour, max_per_day=body.max_per_day,
        status="draft", created_by=p.user.id,
    )
    db.add(item)
    db.flush()
    _event(db, org_id, p.user.id, "outreach.sender_created", "outbound_sender", item.id,
           body.workspace_id, {"email_address": address, "status": "draft"})
    db.commit()
    db.refresh(item)
    return item


@router.patch("/senders/{sender_id}/status", response_model=SenderOut)
def update_sender_status(
    org_id: str, sender_id: str, body: SenderStatusUpdate,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    item = db.query(OutboundSender).filter_by(id=sender_id, org_id=org_id).with_for_update().first()
    if item is None:
        raise HTTPException(404, "Sender not found")
    _write(org_id, item.workspace_id, p, db)
    require_founder_authority(db, org_id, p.user.id)
    if item.status == body.status:
        return item
    item.status = body.status
    if body.status == "active":
        item.approved_by = p.user.id
        item.approved_at = datetime.now(timezone.utc)
    _event(db, org_id, p.user.id, "outreach.sender_status_changed", "outbound_sender", item.id,
           item.workspace_id, {"status": item.status})
    db.commit()
    db.refresh(item)
    return item


@router.get("/consents", response_model=list[ConsentOut])
def list_consents(
    org_id: str, workspace_id: str = Query(min_length=1), contact_id: str | None = None,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    _read(org_id, workspace_id, p, db)
    query = db.query(CommunicationConsent).filter_by(org_id=org_id, workspace_id=workspace_id)
    if contact_id:
        query = query.filter_by(contact_id=contact_id)
    return query.order_by(CommunicationConsent.recorded_at.desc()).limit(500).all()


@router.post("/consents", response_model=ConsentOut, status_code=201)
def record_consent(
    org_id: str, body: ConsentCreate,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    _write(org_id, body.workspace_id, p, db)
    require_founder_authority(db, org_id, p.user.id)
    contact = _lock_contact(db, org_id, body.workspace_id, body.contact_id)
    if contact is None:
        raise HTTPException(404, "Contact not found")
    if len(body.source.strip()) < 2:
        raise HTTPException(422, "Consent source must be non-empty")
    if body.channel == "email" and not contact.email:
        raise HTTPException(422, "Email consent cannot be recorded without a contact email address")
    if body.channel == "phone" and not contact.phone:
        raise HTTPException(422, "Phone consent cannot be recorded without a contact phone number")
    if body.status == "granted" and (body.legal_basis != "consent" or len(body.evidence_reference.strip()) < 3):
        raise HTTPException(422, "Granted consent requires consent basis and evidence reference")
    if body.status == "legitimate_interest_reviewed" and (
        body.legal_basis != "legitimate_interest" or len(body.review_note.strip()) < 10
        or len(body.evidence_reference.strip()) < 3
    ):
        raise HTTPException(422, "Reviewed legitimate-interest status requires review note and evidence reference")
    if body.status == "withdrawn" and len(body.evidence_reference.strip()) < 3:
        raise HTTPException(422, "Consent withdrawal requires an evidence reference")
    recorded_at = body.recorded_at or datetime.now(timezone.utc)
    if recorded_at.tzinfo is None or recorded_at > datetime.now(timezone.utc):
        raise HTTPException(422, "Consent evidence timestamp must be timezone-aware and cannot be in the future")
    item = CommunicationConsent(
        org_id=org_id, workspace_id=body.workspace_id, contact_id=body.contact_id,
        channel=body.channel, status=body.status, legal_basis=body.legal_basis,
        source=body.source.strip(), evidence_reference=body.evidence_reference.strip(),
        review_note=body.review_note.strip(), recorded_at=recorded_at, recorded_by=p.user.id,
    )
    db.add(item)
    db.flush()
    if body.status == "withdrawn":
        _activate_block(db, org_id, body.workspace_id, body.contact_id, body.channel,
                        "opt_out", "consent_record", body.evidence_reference, p.user.id)
        _stop_queued_messages(db, org_id, body.workspace_id, body.contact_id, body.channel,
                              "opt_out", exclude_message_id=None, actor_id=p.user.id)
    _event(db, org_id, p.user.id, "outreach.consent_recorded", "communication_consent", item.id,
           body.workspace_id, {"contact_id": body.contact_id, "channel": body.channel, "status": body.status})
    db.commit()
    db.refresh(item)
    return item


@router.get("/blocks", response_model=list[BlockOut])
def list_blocks(
    org_id: str, workspace_id: str = Query(min_length=1), status: str | None = None,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    _read(org_id, workspace_id, p, db)
    query = db.query(CommunicationBlock).filter_by(org_id=org_id, workspace_id=workspace_id)
    if status:
        if status not in {"active", "released"}:
            raise HTTPException(422, "Unsupported block status")
        query = query.filter_by(status=status)
    return query.order_by(CommunicationBlock.recorded_at.desc()).limit(500).all()


@router.post("/blocks/{block_id}/release", response_model=BlockOut)
def release_block(
    org_id: str, block_id: str, body: BlockRelease,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    item = db.query(CommunicationBlock).filter_by(id=block_id, org_id=org_id).with_for_update().first()
    if item is None:
        raise HTTPException(404, "Communication block not found")
    _write(org_id, item.workspace_id, p, db)
    require_founder_authority(db, org_id, p.user.id)
    if len(body.note.strip()) < 3:
        raise HTTPException(422, "Founder release rationale must be non-empty")
    if item.status != "active":
        raise HTTPException(409, "Communication block is already released")
    latest = _latest_consent(db, org_id, item.workspace_id, item.contact_id, item.channel)
    if item.reason in {"opt_out", "bounce"} and (
        latest is None or latest.recorded_at <= item.recorded_at
        or latest.status not in {"granted", "legitimate_interest_reviewed"}
    ):
        raise HTTPException(403, "Opt-out or bounce block requires newer founder-reviewed channel eligibility evidence")
    if latest is None or latest.status not in {"granted", "legitimate_interest_reviewed"}:
        raise HTTPException(403, "A current eligible channel-consent record is required before release")
    item.status = "released"
    item.released_by = p.user.id
    item.released_at = datetime.now(timezone.utc)
    item.release_note = body.note.strip()
    _event(db, org_id, p.user.id, "outreach.block_released", "communication_block", item.id,
           item.workspace_id, {"contact_id": item.contact_id, "channel": item.channel, "reason": item.reason})
    db.commit()
    db.refresh(item)
    return item


@router.get("/messages", response_model=list[MessageOut])
def list_messages(
    org_id: str, workspace_id: str = Query(min_length=1), status: str | None = None,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    _read(org_id, workspace_id, p, db)
    query = db.query(OutboundMessage).filter_by(org_id=org_id, workspace_id=workspace_id)
    if status:
        query = query.filter_by(status=status)
    return query.order_by(OutboundMessage.created_at.desc()).limit(250).all()


@router.post("/messages", response_model=MessageOut, status_code=201)
def create_message_draft(
    org_id: str, body: MessageCreate,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    _write(org_id, body.workspace_id, p, db)
    sender = db.query(OutboundSender).filter_by(
        id=body.sender_id, org_id=org_id, workspace_id=body.workspace_id,
    ).first()
    if sender is None:
        raise HTTPException(404, "Sender not found")
    contact = db.query(Contact).filter_by(
        id=body.contact_id, org_id=org_id, workspace_id=body.workspace_id,
    ).first()
    if contact is None:
        raise HTTPException(404, "Contact not found")
    if not contact.email:
        raise HTTPException(422, "Contact has no email address")
    if len(body.subject.strip()) < 2 or len(body.body.strip()) < 10:
        raise HTTPException(422, "Email subject and body must contain meaningful text")
    if body.lead_id:
        lead = db.query(Lead).filter_by(
            id=body.lead_id, org_id=org_id, workspace_id=body.workspace_id,
        ).first()
        if lead is None:
            raise HTTPException(404, "Lead not found")
        if lead.contact_id and lead.contact_id != contact.id:
            raise HTTPException(422, "Linked lead and contact do not match")
    item = OutboundMessage(
        org_id=org_id, workspace_id=body.workspace_id, sender_id=sender.id,
        contact_id=contact.id, lead_id=body.lead_id, recipient=contact.email.lower().strip(),
        subject=body.subject.strip(), body=body.body, purpose=body.purpose.strip(),
        sender_snapshot={"display_name": sender.display_name, "email_address": sender.email_address},
        created_by=p.user.id,
    )
    db.add(item)
    db.flush()
    _event(db, org_id, p.user.id, "outreach.message_drafted", "outbound_message", item.id,
           body.workspace_id, {"sender_id": sender.id, "contact_id": contact.id})
    db.commit()
    db.refresh(item)
    return item


@router.post("/messages/{message_id}/submit-for-approval", response_model=MessageOut)
def submit_message_for_approval(
    org_id: str, message_id: str,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    item = db.query(OutboundMessage).filter_by(id=message_id, org_id=org_id).first()
    if item is None:
        raise HTTPException(404, "Outbound message not found")
    _write(org_id, item.workspace_id, p, db)
    _lock_contact(db, org_id, item.workspace_id, item.contact_id)
    item = db.query(OutboundMessage).filter_by(id=message_id, org_id=org_id).with_for_update().first()
    if item is None:
        raise HTTPException(404, "Outbound message not found")
    if item.status not in {"draft", "rejected"}:
        raise HTTPException(409, "Only draft or rejected messages can be submitted")
    sender = db.query(OutboundSender).filter_by(
        id=item.sender_id, org_id=org_id, workspace_id=item.workspace_id,
    ).first()
    if sender is None:
        raise HTTPException(404, "Sender not found")
    contact, consent = _validate_message_sendability(db, org_id, item, sender)
    _check_rate_limits(db, org_id, item, sender)
    item.consent_id = consent.id
    item.consent_snapshot = {
        "id": consent.id, "channel": consent.channel, "status": consent.status,
        "legal_basis": consent.legal_basis, "source": consent.source,
        "evidence_reference": consent.evidence_reference, "recorded_at": consent.recorded_at.isoformat(),
    }
    approval = Approval(
        org_id=org_id, workspace_id=item.workspace_id,
        action_type="external_communication.sensitive", resource_id=item.id,
        idempotency_key=f"outreach-message:{item.id}:{uuid.uuid4()}",
        request_payload={
            "channel": item.channel, "recipient": item.recipient,
            "sender_id": sender.id, "sender": sender.email_address,
            "subject": item.subject, "contact_id": contact.id, "lead_id": item.lead_id,
        },
        requested_by=p.user.id,
    )
    db.add(approval)
    db.flush()
    item.status = "pending_approval"
    item.approval_id = approval.id
    _event(db, org_id, p.user.id, "outreach.message_submitted", "outbound_message", item.id,
           item.workspace_id, {"approval_id": approval.id, "consent_id": consent.id})
    _outbox(db, org_id, item.workspace_id, "outreach.message_submitted", "outbound_message", item.id,
            {"approval_id": approval.id}, key_suffix=approval.id)
    db.commit()
    db.refresh(item)
    return item

 
@router.post("/messages/{message_id}/reject", response_model=MessageOut)
def reject_message(
    org_id: str, message_id: str, body: MessageReject,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    item = db.query(OutboundMessage).filter_by(id=message_id, org_id=org_id).with_for_update().first()
    if item is None:
        raise HTTPException(404, "Outbound message not found")
    require_founder_authority(db, org_id, p.user.id)
    if item.status != "pending_approval" or item.approval_id != body.approval_id:
        raise HTTPException(409, "Outbound message is not awaiting this approval")
    approval = db.query(Approval).filter_by(
        id=body.approval_id, org_id=org_id, workspace_id=item.workspace_id,
        action_type="external_communication.sensitive", resource_id=item.id,
    ).with_for_update().first()
    if approval is None:
        raise HTTPException(404, "Outbound message approval not found")
    if approval.status == ApprovalStatus.pending:
        approval.status = ApprovalStatus.rejected
        approval.decided_by = p.user.id
        approval.decision_note = body.note
        approval.decided_at = datetime.now(timezone.utc)
    elif approval.status != ApprovalStatus.rejected or not approval.decided_by or not has_founder_authority(db, org_id, approval.decided_by):
        raise HTTPException(409, "Outbound message approval is no longer rejectable")
    item.status = "rejected"
    item.stop_reason = "founder_rejected"
    _event(db, org_id, p.user.id, "outreach.message_rejected", "outbound_message", item.id,
           item.workspace_id, {"approval_id": approval.id, "note": body.note})
    db.commit()
    db.refresh(item)
    return item


@router.post("/messages/{message_id}/queue", response_model=MessageOut)
def queue_approved_message(
    org_id: str, message_id: str,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    item = db.query(OutboundMessage).filter_by(id=message_id, org_id=org_id).first()
    if item is None:
        raise HTTPException(404, "Outbound message not found")
    _write(org_id, item.workspace_id, p, db)
    _lock_contact(db, org_id, item.workspace_id, item.contact_id)
    item = db.query(OutboundMessage).filter_by(id=message_id, org_id=org_id).with_for_update().first()
    if item is None:
        raise HTTPException(404, "Outbound message not found")
    if item.status != "pending_approval" or not item.approval_id:
        raise HTTPException(409, "Outbound message is not awaiting approval")
    sender = db.query(OutboundSender).filter_by(
        id=item.sender_id, org_id=org_id, workspace_id=item.workspace_id,
    ).with_for_update().first()
    if sender is None:
        raise HTTPException(404, "Sender not found")
    _validate_message_sendability(db, org_id, item, sender)
    _check_rate_limits(db, org_id, item, sender)
    require_approved_action(
        db, approval_id=item.approval_id, org_id=org_id,
        workspace_id=item.workspace_id, action_type="external_communication.sensitive",
        resource_id=item.id, actor_user_id=p.user.id,
    )
    item.status = "queued"
    item.queued_at = datetime.now(timezone.utc)
    _event(db, org_id, p.user.id, "outreach.message_queued", "outbound_message", item.id,
           item.workspace_id, {"approval_id": item.approval_id, "sender_id": sender.id})
    _outbox(db, org_id, item.workspace_id, "outreach.message_queued", "outbound_message", item.id,
            {"approval_id": item.approval_id, "sender_id": sender.id}, key_suffix=item.approval_id)
    db.commit()
    db.refresh(item)
    return item


def _activate_block(db: Session, org_id: str, workspace_id: str, contact_id: str,
                    channel: str, reason: str, source: str, note: str, actor_id: str):
    block = db.query(CommunicationBlock).filter_by(
        org_id=org_id, workspace_id=workspace_id, contact_id=contact_id, channel=channel,
    ).with_for_update().first()
    if block is None:
        block = CommunicationBlock(
            org_id=org_id, workspace_id=workspace_id, contact_id=contact_id,
            channel=channel, status="active", reason=reason, source=source,
            note=note, recorded_by=actor_id, recorded_at=datetime.now(timezone.utc),
        )
        db.add(block)
    else:
        block.status = "active"
        block.reason = reason
        block.source = source
        block.note = note
        block.recorded_by = actor_id
        block.recorded_at = datetime.now(timezone.utc)
        block.released_by = None
        block.released_at = None
        block.release_note = ""
    db.flush()
    return block


def _stop_queued_messages(db: Session, org_id: str, workspace_id: str, contact_id: str,
                          channel: str, reason: str, exclude_message_id: str | None, actor_id: str):
    query = db.query(OutboundMessage).filter(
        OutboundMessage.org_id == org_id,
        OutboundMessage.workspace_id == workspace_id,
        OutboundMessage.contact_id == contact_id,
        OutboundMessage.channel == channel,
        OutboundMessage.status.in_(["draft", "pending_approval", "queued"]),
    )
    if exclude_message_id:
        query = query.filter(OutboundMessage.id != exclude_message_id)
    for message in query.with_for_update().all():
        if message.status == "pending_approval" and message.approval_id:
            approval = db.query(Approval).filter_by(
                id=message.approval_id, org_id=org_id, workspace_id=workspace_id,
                action_type="external_communication.sensitive", resource_id=message.id,
            ).with_for_update().first()
            if approval and approval.status == ApprovalStatus.pending:
                approval.status = ApprovalStatus.rejected
                approval.decided_by = actor_id
                approval.decision_note = f"Automatically stopped due to {reason}"
                approval.decided_at = datetime.now(timezone.utc)
        message.status = "suppressed" if reason in {"opt_out", "bounce"} else "cancelled"
        message.stop_reason = reason
        _event(db, org_id, actor_id, "outreach.message_stopped", "outbound_message", message.id,
               workspace_id, {"reason": reason, "contact_id": contact_id})


@router.post("/messages/{message_id}/events", response_model=MessageEventOut, status_code=201)
def record_message_stop_event(
    org_id: str, message_id: str, body: StopEventCreate,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    item = db.query(OutboundMessage).filter_by(id=message_id, org_id=org_id).first()
    if item is None:
        raise HTTPException(404, "Outbound message not found")
    _write(org_id, item.workspace_id, p, db)
    _lock_contact(db, org_id, item.workspace_id, item.contact_id)
    item = db.query(OutboundMessage).filter_by(id=message_id, org_id=org_id).with_for_update().first()
    if item is None:
        raise HTTPException(404, "Outbound message not found")
    if body.source != "manual":
        raise HTTPException(403, "Provider events require a signed provider webhook adapter; manual event recording only is enabled")
    if body.event_type not in {"reply", "opt_out", "bounce"}:
        raise HTTPException(422, "Only reply, opt-out and bounce stop events can be recorded manually")
    if len(body.note.strip()) < 3:
        raise HTTPException(422, "A stop-event evidence note is required")
    if item.status not in {"queued", "sent", "delivered"}:
        raise HTTPException(409, "Stop events require a queued or sent message")
    if body.occurred_at and (body.occurred_at.tzinfo is None or body.occurred_at > datetime.now(timezone.utc)):
        raise HTTPException(422, "Event timestamp must be timezone-aware and cannot be in the future")
    if body.external_event_id:
        duplicate = db.query(OutboundMessageEvent).filter_by(
            org_id=org_id, workspace_id=item.workspace_id, external_event_id=body.external_event_id,
        ).first()
        if duplicate:
            if duplicate.message_id != item.id:
                raise HTTPException(409, "Provider event reference already belongs to another message")
            return duplicate
    occurred_at = body.occurred_at or datetime.now(timezone.utc)
    event = OutboundMessageEvent(
        org_id=org_id, workspace_id=item.workspace_id, message_id=item.id,
        event_type=body.event_type, source="manual", external_event_id=body.external_event_id,
        occurred_at=occurred_at, payload={"note": body.note.strip()},
        recorded_by=p.user.id,
    )
    db.add(event)
    db.flush()
    item.status = {"reply": "replied", "opt_out": "opted_out", "bounce": "bounced"}[body.event_type]
    item.stop_reason = body.event_type
    block = _activate_block(
        db, org_id, item.workspace_id, item.contact_id, "email",
        body.event_type, "manual_event", body.note.strip(), p.user.id,
    )
    _stop_queued_messages(
        db, org_id, item.workspace_id, item.contact_id, "email",
        body.event_type, exclude_message_id=item.id, actor_id=p.user.id,
    )
    if body.event_type == "opt_out":
        consent = CommunicationConsent(
            org_id=org_id, workspace_id=item.workspace_id, contact_id=item.contact_id,
            channel="email", status="withdrawn", legal_basis="consent",
            source="manual_opt_out_event", evidence_reference=body.external_event_id or event.id,
            review_note=body.note.strip(), recorded_at=occurred_at, recorded_by=p.user.id,
        )
        db.add(consent)
    _event(db, org_id, p.user.id, "outreach.stop_event_recorded", "outbound_message_event", event.id,
           item.workspace_id, {"message_id": item.id, "event_type": body.event_type, "block_id": block.id})
    _outbox(db, org_id, item.workspace_id, "outreach.stop_event_recorded", "outbound_message_event", event.id,
            {"message_id": item.id, "event_type": body.event_type, "block_id": block.id})
    db.commit()
    db.refresh(event)
    return event


@router.get("/messages/{message_id}/events", response_model=list[MessageEventOut])
def list_message_events(
    org_id: str, message_id: str,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    item = db.query(OutboundMessage).filter_by(id=message_id, org_id=org_id).first()
    if item is None:
        raise HTTPException(404, "Outbound message not found")
    _read(org_id, item.workspace_id, p, db)
    return (db.query(OutboundMessageEvent).filter_by(
        org_id=org_id, workspace_id=item.workspace_id, message_id=item.id,
    ).order_by(OutboundMessageEvent.occurred_at.asc()).all())
