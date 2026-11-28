"""Workspace-scoped Revenue and Delivery API routes."""
from datetime import datetime, timezone
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_principal, has_founder_authority, require_membership, require_role, require_founder_authority, require_workspace_access_from_context, Principal
from app.db import get_db
from app.data_protection import DataProtectionBlocked, sanitize_text
from app.models import Role, EvaluationRun, Workspace
from app.audit import record_event
from app.telephony.models import OutboxEvent
from app.domain_models import Client, Contact, ContactActivity, Lead, LeadResearchRecord, OutreachDraft, Opportunity, Project, Milestone, ProjectOutcome, OutcomeMeasurement
from app.domain_schemas import (
    ClientCreate, ClientOut, ContactCreate, ContactOut, ContactActivityCreate, ContactActivityOut, LeadCreate, LeadOut, LeadResearchCreate, LeadResearchOut, OutreachDraftCreate, OutreachDraftReview, OutreachDraftOut,
    LeadStageUpdate, OpportunityCreate, OpportunityOut, OpportunityStageUpdate,
    ProjectCreate, ProjectOut, ProjectStatusUpdate, MilestoneCreate,
    MilestoneOut, MilestoneStatusUpdate, ProjectOutcomeCreate, ProjectOutcomeOut,
    OutcomeMeasurementCreate, OutcomeMeasurementOut, OutcomeAcceptanceDecision,
)

router = APIRouter(prefix="/v1/orgs/{org_id}", tags=["revenue-delivery"])
WRITERS = {Role.owner, Role.admin, Role.operator}


def _workspace(db: Session, org_id: str, workspace_id: str) -> None:
    require_workspace_access_from_context(org_id, workspace_id, db)


def _scoped_parent(db: Session, model, *, object_id: str, org_id: str, workspace_id: str, label: str):
    _workspace(db, org_id, workspace_id)
    item = db.query(model).filter_by(
        id=object_id, org_id=org_id, workspace_id=workspace_id
    ).first()
    if item is None:
        raise HTTPException(404, f"{label} not found")
    return item


def _write_access(org_id: str, p: Principal, db: Session, workspace_id: str) -> None:
    role = require_membership(org_id, p, db)
    if role not in WRITERS and not has_founder_authority(db, org_id, p.user.id):
        require_role(role, WRITERS)
    _workspace(db, org_id, workspace_id)


def _event(db, org_id, actor_id, event_type, resource_type, resource_id, workspace_id, payload=None):
    record_event(
        db, org_id, actor_id, event_type, resource_type, resource_id,
        workspace_id, payload or {},
    )


@router.get("/clients", response_model=list[ClientOut])
def list_clients(
    org_id: str,
    workspace_id: str = Query(min_length=1),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    require_membership(org_id, p, db)
    _workspace(db, org_id, workspace_id)
    return (db.query(Client).filter_by(org_id=org_id, workspace_id=workspace_id)
            .order_by(Client.created_at.desc()).limit(limit).all())


@router.post("/clients", response_model=ClientOut, status_code=201)
def create_client(
    org_id: str, body: ClientCreate,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    _write_access(org_id, p, db, body.workspace_id)
    if body.external_key:
        existing = db.query(Client).filter_by(
            org_id=org_id, workspace_id=body.workspace_id,
            external_key=body.external_key,
        ).first()
        if existing:
            raise HTTPException(409, "Client external key already exists")
    item = Client(org_id=org_id, workspace_id=body.workspace_id,
                  name=body.name, legal_name=body.legal_name,
                  external_key=body.external_key, industry=body.industry,
                  website=body.website, notes=body.notes, created_by=p.user.id)
    db.add(item)
    db.flush()
    _event(db, org_id, p.user.id, "client.created", "client", item.id,
           body.workspace_id)
    db.commit()
    db.refresh(item)
    return item


@router.get("/contacts", response_model=list[ContactOut])
def list_contacts(
    org_id: str,
    workspace_id: str = Query(min_length=1),
    client_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    require_membership(org_id, p, db)
    _workspace(db, org_id, workspace_id)
    query = db.query(Contact).filter_by(org_id=org_id, workspace_id=workspace_id)
    if client_id:
        _scoped_parent(db, Client, object_id=client_id, org_id=org_id,
                       workspace_id=workspace_id, label="Client")
        query = query.filter_by(client_id=client_id)
    return query.order_by(Contact.created_at.desc()).limit(limit).all()


@router.post("/contacts", response_model=ContactOut, status_code=201)
def create_contact(
    org_id: str, body: ContactCreate,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    _write_access(org_id, p, db, body.workspace_id)
    if body.client_id:
        _scoped_parent(db, Client, object_id=body.client_id, org_id=org_id,
                       workspace_id=body.workspace_id, label="Client")
    normalized_email = body.email.lower().strip()
    if body.phone_call_consent_status == "granted":
        require_founder_authority(db, org_id, p.user.id)
        if not body.phone_call_consent_source.strip() or body.phone_call_consent_recorded_at is None:
            raise HTTPException(422, "Granted phone-call consent requires source and recorded timestamp")
    if normalized_email:
        duplicate = db.query(Contact).filter_by(
            org_id=org_id, workspace_id=body.workspace_id,
            email=normalized_email,
        ).first()
        if duplicate:
            raise HTTPException(409, "Potential duplicate contact exists in this workspace; review and link the existing record")
    item = Contact(org_id=org_id, workspace_id=body.workspace_id,
                   client_id=body.client_id, first_name=body.first_name,
                   last_name=body.last_name, email=normalized_email,
                   phone=body.phone, job_title=body.job_title, source=body.source,
                   consent_status=body.consent_status,
                   phone_call_consent_status=body.phone_call_consent_status,
                   phone_call_consent_source=body.phone_call_consent_source.strip(),
                   phone_call_consent_recorded_at=body.phone_call_consent_recorded_at,
                   created_by=p.user.id)
    db.add(item)
    db.flush()
    _event(db, org_id, p.user.id, "contact.created", "contact", item.id,
           body.workspace_id, {"client_id": item.client_id})
    db.commit()
    db.refresh(item)
    return item


@router.get("/contacts/{contact_id}/activities", response_model=list[ContactActivityOut])
def list_contact_activities(
    org_id: str, contact_id: str,
    workspace_id: str = Query(min_length=1),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    require_membership(org_id, p, db)
    _workspace(db, org_id, workspace_id)
    _scoped_parent(db, Contact, object_id=contact_id, org_id=org_id,
                   workspace_id=workspace_id, label="Contact")
    return (db.query(ContactActivity).filter_by(
        org_id=org_id, workspace_id=workspace_id, contact_id=contact_id,
    ).order_by(ContactActivity.occurred_at.desc(), ContactActivity.created_at.desc())
     .limit(limit).all())


@router.post("/contact-activities", response_model=ContactActivityOut, status_code=201)
def create_contact_activity(
    org_id: str, body: ContactActivityCreate,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    _write_access(org_id, p, db, body.workspace_id)
    _scoped_parent(db, Contact, object_id=body.contact_id, org_id=org_id,
                   workspace_id=body.workspace_id, label="Contact")
    item = ContactActivity(
        org_id=org_id, workspace_id=body.workspace_id, contact_id=body.contact_id,
        activity_type=body.activity_type, direction=body.direction,
        subject=body.subject.strip(), body=body.body,
        outcome=body.outcome.strip(), source_reference=body.source_reference.strip(),
        occurred_at=body.occurred_at or datetime.now(timezone.utc),
        created_by=p.user.id,
    )
    db.add(item)
    db.flush()
    _event(db, org_id, p.user.id, "contact.activity_recorded", "contact_activity",
           item.id, body.workspace_id, {"contact_id": body.contact_id,
           "activity_type": item.activity_type, "direction": item.direction})
    db.commit()
    db.refresh(item)
    return item


@router.get("/leads", response_model=list[LeadOut])
def list_leads(
    org_id: str,
    workspace_id: str = Query(min_length=1),
    stage: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    require_membership(org_id, p, db)
    _workspace(db, org_id, workspace_id)
    query = db.query(Lead).filter_by(org_id=org_id, workspace_id=workspace_id)
    if stage:
        query = query.filter_by(stage=stage)
    return query.order_by(Lead.created_at.desc()).limit(limit).all()


@router.post("/leads", response_model=LeadOut, status_code=201)
def create_lead(
    org_id: str, body: LeadCreate,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    _write_access(org_id, p, db, body.workspace_id)
    if body.client_id:
        _scoped_parent(db, Client, object_id=body.client_id, org_id=org_id,
                       workspace_id=body.workspace_id, label="Client")
    contact = None
    if body.contact_id:
        contact = _scoped_parent(db, Contact, object_id=body.contact_id, org_id=org_id,
                                 workspace_id=body.workspace_id, label="Contact")
        if body.client_id and contact.client_id and contact.client_id != body.client_id:
            raise HTTPException(422, "Lead contact must belong to the selected client")
    client_id = body.client_id or (contact.client_id if contact else None)
    # Serialize duplicate checks per workspace so concurrent lead creation cannot
    # both pass the check before either transaction commits.
    db.query(Workspace).filter_by(id=body.workspace_id, org_id=org_id).with_for_update().first()
    normalized_email = (body.email or (contact.email if contact else "")).lower().strip()
    candidate_emails = {
        value.lower().strip()
        for value in (body.email, contact.email if contact else "")
        if value and value.strip()
    }
    duplicate = None
    if candidate_emails:
        duplicate = db.query(Lead).filter(
            Lead.org_id == org_id,
            Lead.workspace_id == body.workspace_id,
            Lead.email.in_(candidate_emails),
        ).first()
    if duplicate is None and body.contact_id:
        duplicate = db.query(Lead).filter_by(
            org_id=org_id, workspace_id=body.workspace_id, contact_id=body.contact_id,
        ).first()
    if duplicate is not None:
        raise HTTPException(
            409,
            "Potential duplicate lead exists in this workspace; review and update the existing lead instead.",
        )
    item = Lead(org_id=org_id, workspace_id=body.workspace_id,
                client_id=client_id, contact_id=body.contact_id,
                company_name=body.company_name, contact_name=body.contact_name,
                email=normalized_email, source=body.source,
                score=body.score, qualification_notes=body.qualification_notes,
                created_by=p.user.id)
    db.add(item)
    db.flush()
    _event(db, org_id, p.user.id, "lead.created", "lead", item.id,
           body.workspace_id, {"source": item.source, "stage": item.stage})
    db.commit()
    db.refresh(item)
    return item


@router.patch("/leads/{lead_id}", response_model=LeadOut)
def update_lead_stage(
    org_id: str, lead_id: str, body: LeadStageUpdate,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    item = db.query(Lead).filter_by(id=lead_id, org_id=org_id).first()
    if item is None:
        raise HTTPException(404, "Lead not found")
    _write_access(org_id, p, db, item.workspace_id)
    if body.stage == "suppressed" and not body.suppression_reason.strip():
        raise HTTPException(422, "A suppression reason is required")
    item.stage = body.stage
    item.suppression_reason = body.suppression_reason if body.stage == "suppressed" else ""
    _event(db, org_id, p.user.id, "lead.stage_changed", "lead", item.id,
           item.workspace_id, {"stage": item.stage})
    db.commit()
    db.refresh(item)
    return item


@router.get("/leads/{lead_id}/research", response_model=list[LeadResearchOut])
def list_lead_research(
    org_id: str, lead_id: str, workspace_id: str = Query(min_length=1),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    require_membership(org_id, p, db)
    _workspace(db, org_id, workspace_id)
    _scoped_parent(db, Lead, object_id=lead_id, org_id=org_id,
                   workspace_id=workspace_id, label="Lead")
    return (db.query(LeadResearchRecord).filter_by(
        org_id=org_id, workspace_id=workspace_id, lead_id=lead_id,
    ).order_by(LeadResearchRecord.researched_at.desc()).limit(limit).all())


@router.post("/lead-research", response_model=LeadResearchOut, status_code=201)
def create_lead_research(
    org_id: str, body: LeadResearchCreate,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    _write_access(org_id, p, db, body.workspace_id)
    lead = _scoped_parent(db, Lead, object_id=body.lead_id, org_id=org_id,
                          workspace_id=body.workspace_id, label="Lead")
    if lead.stage == "suppressed":
        raise HTTPException(409, "Suppressed leads cannot receive new research activity")
    now = datetime.now(timezone.utc)
    researched_at = body.researched_at or now
    if researched_at.tzinfo is None or researched_at > now:
        raise HTTPException(422, "Research timestamp must be timezone-aware and cannot be in the future")
    references = []
    for source in body.source_references:
        parsed = urlsplit(source.url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise HTTPException(422, "Research source references must be valid HTTPS URLs without embedded credentials")
        if source.accessed_at.tzinfo is None or source.accessed_at > now:
            raise HTTPException(422, "Source access timestamps must be timezone-aware and cannot be in the future")
        if source.published_at and source.published_at.tzinfo is None:
            raise HTTPException(422, "Source publication timestamps must include a timezone")
        references.append(source.model_dump(mode="json"))
    item = LeadResearchRecord(
        org_id=org_id, workspace_id=body.workspace_id, lead_id=lead.id,
        summary=body.summary, fit_score=body.fit_score,
        confidence_score=body.confidence_score, buying_signals=body.buying_signals,
        risks=body.risks, source_references=references,
        researched_at=researched_at,
        created_by=p.user.id,
    )
    db.add(item)
    db.flush()
    _event(db, org_id, p.user.id, "lead.research_recorded", "lead_research", item.id,
           body.workspace_id, {"lead_id": lead.id, "fit_score": item.fit_score,
                               "confidence_score": item.confidence_score,
                               "source_count": len(references)})
    db.add(OutboxEvent(
        org_id=org_id, workspace_id=body.workspace_id,
        event_type="revenue.lead_research_recorded", schema_version=1,
        aggregate_type="lead_research", aggregate_id=item.id,
        idempotency_key="lead-research-recorded:" + item.id,
        payload={"lead_id": lead.id, "fit_score": item.fit_score},
    ))
    db.commit()
    db.refresh(item)
    return item


@router.get("/outreach-drafts", response_model=list[OutreachDraftOut])
def list_outreach_drafts(
    org_id: str,
    workspace_id: str = Query(min_length=1), status: str | None = None,
    limit: int = Query(default=100, ge=1, le=300),
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    require_membership(org_id, p, db)
    _workspace(db, org_id, workspace_id)
    query = db.query(OutreachDraft).filter_by(org_id=org_id, workspace_id=workspace_id)
    if status:
        if status not in {"draft", "approved_draft", "rejected"}:
            raise HTTPException(422, "Unsupported outreach draft status")
        query = query.filter_by(status=status)
    return query.order_by(OutreachDraft.created_at.desc()).limit(limit).all()


@router.post("/outreach-drafts", response_model=OutreachDraftOut, status_code=201)
def create_outreach_draft(
    org_id: str, body: OutreachDraftCreate,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    _write_access(org_id, p, db, body.workspace_id)
    lead = _scoped_parent(db, Lead, object_id=body.lead_id, org_id=org_id,
                          workspace_id=body.workspace_id, label="Lead")
    if lead.stage in {"suppressed", "unqualified"}:
        raise HTTPException(409, "Suppressed or unqualified leads cannot receive outreach drafts")
    contact_id = body.contact_id or lead.contact_id
    contact = None
    if contact_id:
        contact = _scoped_parent(db, Contact, object_id=contact_id, org_id=org_id,
                                 workspace_id=body.workspace_id, label="Contact")
        if lead.contact_id != contact.id and (not lead.client_id or contact.client_id != lead.client_id):
            raise HTTPException(422, "Outreach contact must be linked to the lead or its client")
    if body.channel == "email" and not ((contact.email if contact else "") or lead.email):
        raise HTTPException(422, "Email outreach drafts require a lead email or linked contact with an email address")
    if body.source_research_ids:
        research = db.query(LeadResearchRecord.id).filter(
            LeadResearchRecord.org_id == org_id,
            LeadResearchRecord.workspace_id == body.workspace_id,
            LeadResearchRecord.lead_id == lead.id,
            LeadResearchRecord.id.in_(body.source_research_ids),
        ).all()
        if len(research) != len(set(body.source_research_ids)):
            raise HTTPException(422, "Every cited research record must belong to this lead and workspace")
    item = OutreachDraft(
        org_id=org_id, workspace_id=body.workspace_id, lead_id=lead.id,
        contact_id=contact_id, channel=body.channel, subject=body.subject.strip(),
        body=body.body, personalization_basis=body.personalization_basis,
        source_research_ids=list(dict.fromkeys(body.source_research_ids)),
        created_by=p.user.id,
    )
    db.add(item)
    db.flush()
    _event(db, org_id, p.user.id, "outreach.draft_created", "outreach_draft", item.id,
           body.workspace_id, {"lead_id": lead.id, "channel": item.channel,
                               "source_research_count": len(item.source_research_ids)})
    db.add(OutboxEvent(
        org_id=org_id, workspace_id=body.workspace_id,
        event_type="revenue.outreach_draft_created", schema_version=1,
        aggregate_type="outreach_draft", aggregate_id=item.id,
        idempotency_key="outreach-draft-created:" + item.id,
        payload={"lead_id": lead.id, "channel": item.channel},
    ))
    db.commit()
    db.refresh(item)
    return item


@router.post("/outreach-drafts/{draft_id}/review", response_model=OutreachDraftOut)
def review_outreach_draft(
    org_id: str, draft_id: str, body: OutreachDraftReview,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    item = db.query(OutreachDraft).filter_by(id=draft_id, org_id=org_id).with_for_update().first()
    if item is None:
        raise HTTPException(404, "Outreach draft not found")
    require_founder_authority(db, org_id, p.user.id)
    _workspace(db, org_id, item.workspace_id)
    if item.status != "draft":
        raise HTTPException(409, "Only an unreviewed draft can be reviewed")
    item.status = "approved_draft" if body.decision == "approve_draft" else "rejected"
    item.reviewed_by = p.user.id
    item.reviewed_at = datetime.now(timezone.utc)
    item.review_note = body.note
    _event(db, org_id, p.user.id, "outreach.draft_reviewed", "outreach_draft", item.id,
           item.workspace_id, {"decision": item.status})
    db.add(OutboxEvent(
        org_id=org_id, workspace_id=item.workspace_id,
        event_type="revenue.outreach_draft_reviewed", schema_version=1,
        aggregate_type="outreach_draft", aggregate_id=item.id,
        idempotency_key="outreach-draft-reviewed:" + item.id,
        payload={"decision": item.status},
    ))
    db.commit()
    db.refresh(item)
    return item


@router.get("/opportunities", response_model=list[OpportunityOut])
def list_opportunities(
    org_id: str,
    workspace_id: str = Query(min_length=1),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    require_membership(org_id, p, db)
    _workspace(db, org_id, workspace_id)
    return (db.query(Opportunity).filter_by(org_id=org_id, workspace_id=workspace_id)
            .order_by(Opportunity.created_at.desc()).limit(limit).all())


@router.post("/opportunities", response_model=OpportunityOut, status_code=201)
def create_opportunity(
    org_id: str, body: OpportunityCreate,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    _write_access(org_id, p, db, body.workspace_id)
    if body.client_id:
        _scoped_parent(db, Client, object_id=body.client_id, org_id=org_id,
                       workspace_id=body.workspace_id, label="Client")
    lead = None
    if body.lead_id:
        lead = _scoped_parent(db, Lead, object_id=body.lead_id, org_id=org_id,
                              workspace_id=body.workspace_id, label="Lead")
        if lead.stage in {"suppressed", "unqualified"}:
            raise HTTPException(409, "Suppressed or unqualified leads cannot create opportunities")
        if body.client_id and lead.client_id and body.client_id != lead.client_id:
            raise HTTPException(422, "Opportunity client must match the linked lead's client")
    client_id = body.client_id or (lead.client_id if lead else None)
    item = Opportunity(org_id=org_id, workspace_id=body.workspace_id,
                       client_id=client_id, lead_id=body.lead_id,
                       title=body.title, amount_minor=body.amount_minor,
                       currency=body.currency, probability=body.probability,
                       expected_close_date=body.expected_close_date,
                       owner_user_id=p.user.id)
    db.add(item)
    db.flush()
    _event(db, org_id, p.user.id, "opportunity.created", "opportunity",
           item.id, body.workspace_id, {"stage": item.stage})
    db.commit()
    db.refresh(item)
    return item


@router.patch("/opportunities/{opportunity_id}", response_model=OpportunityOut)
def update_opportunity_stage(
    org_id: str, opportunity_id: str, body: OpportunityStageUpdate,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    item = db.query(Opportunity).filter_by(id=opportunity_id, org_id=org_id).first()
    if item is None:
        raise HTTPException(404, "Opportunity not found")
    _write_access(org_id, p, db, item.workspace_id)
    if "client_id" in body.model_fields_set:
        if body.client_id is not None:
            _scoped_parent(db, Client, object_id=body.client_id, org_id=org_id,
                           workspace_id=item.workspace_id, label="Client")
        item.client_id = body.client_id
    item.stage = body.stage
    if body.stage == "won":
        item.probability = 100
    elif body.stage == "lost":
        item.probability = 0
    _event(db, org_id, p.user.id, "opportunity.stage_changed",
           "opportunity", item.id, item.workspace_id,
           {"stage": item.stage, "client_id": item.client_id})
    db.commit()
    db.refresh(item)
    return item



def _protect_outcome_text(value: str) -> tuple[str, dict[str, int]]:
    try:
        return sanitize_text(value)
    except DataProtectionBlocked as exc:
        raise HTTPException(422, "Text rejected by data-protection policy") from exc



def _outcome_payload(db: Session, item: ProjectOutcome) -> dict:
    latest = db.query(OutcomeMeasurement).filter_by(
        org_id=item.org_id, workspace_id=item.workspace_id, outcome_id=item.id,
    ).order_by(OutcomeMeasurement.measured_at.desc(), OutcomeMeasurement.created_at.desc()).first()
    count = db.query(OutcomeMeasurement.id).filter_by(
        org_id=item.org_id, workspace_id=item.workspace_id, outcome_id=item.id,
    ).count()
    if latest is None:
        impact_status = "not_measured"
    elif (
        (item.direction == "increase" and latest.value >= item.target_value)
        or (item.direction == "decrease" and latest.value <= item.target_value)
    ):
        impact_status = "target_met"
    else:
        impact_status = "target_missed"
    return {
        "id": item.id, "workspace_id": item.workspace_id, "project_id": item.project_id,
        "title": item.title, "problem_statement": item.problem_statement,
        "desired_outcome": item.desired_outcome, "metric_name": item.metric_name,
        "metric_unit": item.metric_unit, "direction": item.direction,
        "baseline_value": item.baseline_value, "target_value": item.target_value,
        "target_date": item.target_date, "measurement_method": item.measurement_method,
        "acceptance_criteria": item.acceptance_criteria,
        "delivery_acceptance_status": item.delivery_acceptance_status,
        "acceptance_results": item.acceptance_results,
        "acceptance_note": item.acceptance_note,
        "decided_by_user_id": item.decided_by_user_id, "decided_at": item.decided_at,
        "latest_value": latest.value if latest else None,
        "latest_measured_at": latest.measured_at if latest else None,
        "measurement_count": count, "impact_status": impact_status,
        "created_at": item.created_at,
    }


@router.get("/projects/{project_id}/outcomes", response_model=list[ProjectOutcomeOut])
def list_project_outcomes(
    org_id: str, project_id: str,
    workspace_id: str = Query(min_length=1),
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    require_membership(org_id, p, db)
    _workspace(db, org_id, workspace_id)
    _scoped_parent(db, Project, object_id=project_id, org_id=org_id,
                   workspace_id=workspace_id, label="Project")
    rows = (db.query(ProjectOutcome).filter_by(
        org_id=org_id, workspace_id=workspace_id, project_id=project_id,
    ).order_by(ProjectOutcome.created_at.asc()).limit(100).all())
    return [_outcome_payload(db, item) for item in rows]


@router.post("/projects/{project_id}/outcomes", response_model=ProjectOutcomeOut, status_code=201)
def create_project_outcome(
    org_id: str, project_id: str, body: ProjectOutcomeCreate,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    _write_access(org_id, p, db, body.workspace_id)
    _scoped_parent(db, Project, object_id=project_id, org_id=org_id,
                   workspace_id=body.workspace_id, label="Project")
    protected_fields = {
        "title": body.title, "problem_statement": body.problem_statement,
        "desired_outcome": body.desired_outcome, "metric_name": body.metric_name,
        "metric_unit": body.metric_unit, "measurement_method": body.measurement_method,
    }
    protected_text = {}
    redactions = {}
    for key, value in protected_fields.items():
        protected_text[key], found = _protect_outcome_text(value.strip())
        redactions.update({name: redactions.get(name, 0) + count for name, count in found.items()})
    criteria = []
    for value in body.acceptance_criteria:
        cleaned, found = _protect_outcome_text(value.strip())
        criteria.append(cleaned)
        redactions.update({name: redactions.get(name, 0) + count for name, count in found.items()})
    if any(not value for value in criteria) or len({value.casefold() for value in criteria}) != len(criteria):
        raise HTTPException(422, "Acceptance criteria must be non-empty and unique")
    if any(not value for value in protected_text.values()):
        raise HTTPException(422, "Outcome text fields must not be blank")
    if body.baseline_value is not None:
        if body.baseline_value == body.target_value:
            raise HTTPException(422, "Baseline and target must differ")
        if body.direction == "increase" and body.target_value <= body.baseline_value:
            raise HTTPException(422, "An increase target must exceed its baseline")
        if body.direction == "decrease" and body.target_value >= body.baseline_value:
            raise HTTPException(422, "A decrease target must be below its baseline")
    item = ProjectOutcome(
        org_id=org_id, workspace_id=body.workspace_id, project_id=project_id,
        title=protected_text["title"], problem_statement=protected_text["problem_statement"],
        desired_outcome=protected_text["desired_outcome"], metric_name=protected_text["metric_name"],
        metric_unit=protected_text["metric_unit"], direction=body.direction,
        baseline_value=body.baseline_value, target_value=body.target_value,
        target_date=body.target_date, measurement_method=protected_text["measurement_method"],
        acceptance_criteria=criteria, owner_user_id=p.user.id,
    )
    db.add(item)
    db.flush()
    _event(db, org_id, p.user.id, "delivery.outcome_defined", "project_outcome",
           item.id, body.workspace_id, {"project_id": project_id, "metric_name": item.metric_name,
                                       "redaction_counts": redactions})
    db.commit()
    db.refresh(item)
    return _outcome_payload(db, item)


@router.get("/projects/{project_id}/outcome-measurements", response_model=list[OutcomeMeasurementOut])
def list_project_outcome_measurements(
    org_id: str, project_id: str,
    workspace_id: str = Query(min_length=1),
    limit: int = Query(default=500, ge=1, le=1000),
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    require_membership(org_id, p, db)
    _workspace(db, org_id, workspace_id)
    _scoped_parent(db, Project, object_id=project_id, org_id=org_id,
                   workspace_id=workspace_id, label="Project")
    outcome_ids = select(ProjectOutcome.id).where(
        ProjectOutcome.org_id == org_id,
        ProjectOutcome.workspace_id == workspace_id,
        ProjectOutcome.project_id == project_id,
    )
    return (db.query(OutcomeMeasurement).filter(
        OutcomeMeasurement.org_id == org_id,
        OutcomeMeasurement.workspace_id == workspace_id,
        OutcomeMeasurement.outcome_id.in_(outcome_ids),
    ).order_by(OutcomeMeasurement.measured_at.desc(), OutcomeMeasurement.created_at.desc())
     .limit(limit).all())


@router.get("/outcomes/{outcome_id}/measurements", response_model=list[OutcomeMeasurementOut])
def list_outcome_measurements(
    org_id: str, outcome_id: str,
    workspace_id: str = Query(min_length=1),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    require_membership(org_id, p, db)
    _workspace(db, org_id, workspace_id)
    _scoped_parent(db, ProjectOutcome, object_id=outcome_id, org_id=org_id,
                   workspace_id=workspace_id, label="Project outcome")
    return (db.query(OutcomeMeasurement).filter_by(
        org_id=org_id, workspace_id=workspace_id, outcome_id=outcome_id,
    ).order_by(OutcomeMeasurement.measured_at.desc(), OutcomeMeasurement.created_at.desc())
     .limit(limit).all())


@router.post("/outcomes/{outcome_id}/measurements", response_model=OutcomeMeasurementOut, status_code=201)
def create_outcome_measurement(
    org_id: str, outcome_id: str, body: OutcomeMeasurementCreate,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    _write_access(org_id, p, db, body.workspace_id)
    outcome = _scoped_parent(db, ProjectOutcome, object_id=outcome_id, org_id=org_id,
                             workspace_id=body.workspace_id, label="Project outcome")
    measured_at = body.measured_at or datetime.now(timezone.utc)
    if measured_at.tzinfo is None or measured_at.utcoffset() is None:
        raise HTTPException(422, "Outcome measurement timestamps must include a timezone")
    if measured_at > datetime.now(timezone.utc):
        raise HTTPException(422, "Outcome measurements cannot be future-dated")
    if body.supporting_evaluation_run_id:
        evaluation = db.query(EvaluationRun).filter_by(
            id=body.supporting_evaluation_run_id, org_id=org_id,
            workspace_id=body.workspace_id,
        ).first()
        if evaluation is None:
            raise HTTPException(404, "Supporting evaluation run not found in this workspace")
    if body.milestone_id:
        milestone = _scoped_parent(
            db, Milestone, object_id=body.milestone_id, org_id=org_id,
            workspace_id=body.workspace_id, label="Milestone",
        )
        if milestone.project_id != outcome.project_id:
            raise HTTPException(404, "Milestone not found in this project")
    source_reference, source_redactions = _protect_outcome_text(body.source_reference.strip())
    evidence_summary, evidence_redactions = _protect_outcome_text(body.evidence_summary.strip())
    if not source_reference or not evidence_summary:
        raise HTTPException(422, "Measurement source and evidence summary must not be blank")
    item = OutcomeMeasurement(
        org_id=org_id, workspace_id=body.workspace_id, outcome_id=outcome.id,
        value=body.value, measured_at=measured_at, source_type=body.source_type,
        source_reference=source_reference,
        evidence_summary=evidence_summary,
        supporting_evaluation_run_id=body.supporting_evaluation_run_id,
        milestone_id=body.milestone_id, created_by=p.user.id,
    )
    db.add(item)
    db.flush()
    _event(db, org_id, p.user.id, "delivery.outcome_measured", "outcome_measurement",
           item.id, body.workspace_id, {
               "outcome_id": outcome.id, "source_type": item.source_type,
               "supporting_evaluation_run_id": item.supporting_evaluation_run_id,
               "redaction_counts": {
                   key: source_redactions.get(key, 0) + evidence_redactions.get(key, 0)
                   for key in set(source_redactions) | set(evidence_redactions)
               },
           })
    db.commit()
    db.refresh(item)
    return item


@router.post("/outcomes/{outcome_id}/acceptance", response_model=ProjectOutcomeOut)
def decide_outcome_delivery_acceptance(
    org_id: str, outcome_id: str, body: OutcomeAcceptanceDecision,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    require_membership(org_id, p, db)
    require_founder_authority(db, org_id, p.user.id)
    _workspace(db, org_id, body.workspace_id)
    item = db.query(ProjectOutcome).filter_by(
        id=outcome_id, org_id=org_id, workspace_id=body.workspace_id,
    ).with_for_update().first()
    if item is None:
        raise HTTPException(404, "Project outcome not found")
    if item.delivery_acceptance_status != "pending":
        raise HTTPException(409, "Delivery acceptance has already been decided")
    expected = set(item.acceptance_criteria)
    supplied = set(body.criteria_results)
    if supplied != expected:
        raise HTTPException(422, "Acceptance results must cover the exact agreed criteria")
    if body.decision == "accepted" and not all(body.criteria_results.values()):
        raise HTTPException(409, "Delivery cannot be accepted while an agreed criterion is unmet")
    if body.decision == "rejected" and all(body.criteria_results.values()):
        raise HTTPException(422, "A rejected delivery must identify at least one unmet criterion")
    acceptance_note, note_redactions = _protect_outcome_text(body.note.strip())
    if not acceptance_note:
        raise HTTPException(422, "Acceptance note must not be blank")
    item.delivery_acceptance_status = body.decision
    item.acceptance_results = body.criteria_results
    item.acceptance_note = acceptance_note
    item.decided_by_user_id = p.user.id
    item.decided_at = datetime.now(timezone.utc)
    _event(db, org_id, p.user.id, "delivery.outcome_" + body.decision,
           "project_outcome", item.id, body.workspace_id,
           {"criteria_results": body.criteria_results, "redaction_counts": note_redactions})
    db.commit()
    db.refresh(item)
    return _outcome_payload(db, item)


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(
    org_id: str,
    workspace_id: str = Query(min_length=1),
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    require_membership(org_id, p, db)
    _workspace(db, org_id, workspace_id)
    query = db.query(Project).filter_by(org_id=org_id, workspace_id=workspace_id)
    if status:
        query = query.filter_by(status=status)
    return query.order_by(Project.created_at.desc()).limit(limit).all()


@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(
    org_id: str, body: ProjectCreate,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    _write_access(org_id, p, db, body.workspace_id)
    if body.client_id:
        _scoped_parent(db, Client, object_id=body.client_id, org_id=org_id,
                       workspace_id=body.workspace_id, label="Client")
    if body.opportunity_id:
        _scoped_parent(db, Opportunity, object_id=body.opportunity_id, org_id=org_id,
                       workspace_id=body.workspace_id, label="Opportunity")
    item = Project(org_id=org_id, workspace_id=body.workspace_id,
                   client_id=body.client_id, opportunity_id=body.opportunity_id,
                   name=body.name, description=body.description,
                   priority=body.priority, budget_minor=body.budget_minor,
                   contract_value_minor=body.contract_value_minor,
                   estimated_hours=body.estimated_hours,
                   currency=body.currency, start_date=body.start_date,
                   due_date=body.due_date, owner_user_id=p.user.id)
    db.add(item)
    db.flush()
    _event(db, org_id, p.user.id, "project.created", "project", item.id,
           body.workspace_id, {"status": item.status})
    db.commit()
    db.refresh(item)
    return item


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project_status(
    org_id: str, project_id: str, body: ProjectStatusUpdate,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    item = db.query(Project).filter_by(id=project_id, org_id=org_id).first()
    if item is None:
        raise HTTPException(404, "Project not found")
    _write_access(org_id, p, db, item.workspace_id)
    item.status = body.status
    _event(db, org_id, p.user.id, "project.status_changed", "project",
           item.id, item.workspace_id, {"status": item.status})
    db.commit()
    db.refresh(item)
    return item


@router.get("/projects/{project_id}/milestones", response_model=list[MilestoneOut])
def list_milestones(
    org_id: str, project_id: str,
    workspace_id: str = Query(min_length=1),
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    require_membership(org_id, p, db)
    _workspace(db, org_id, workspace_id)
    _scoped_parent(db, Project, object_id=project_id, org_id=org_id,
                   workspace_id=workspace_id, label="Project")
    return (db.query(Milestone).filter_by(org_id=org_id, workspace_id=workspace_id,
                                         project_id=project_id)
            .order_by(Milestone.sort_order.asc(), Milestone.created_at.asc()).all())


@router.post("/milestones", response_model=MilestoneOut, status_code=201)
def create_milestone(
    org_id: str, body: MilestoneCreate,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    _write_access(org_id, p, db, body.workspace_id)
    _scoped_parent(db, Project, object_id=body.project_id, org_id=org_id,
                   workspace_id=body.workspace_id, label="Project")
    item = Milestone(org_id=org_id, workspace_id=body.workspace_id,
                     project_id=body.project_id, title=body.title,
                     description=body.description, due_date=body.due_date,
                     sort_order=body.sort_order)
    db.add(item)
    db.flush()
    _event(db, org_id, p.user.id, "milestone.created", "milestone",
           item.id, body.workspace_id, {"project_id": body.project_id})
    db.commit()
    db.refresh(item)
    return item


@router.patch("/milestones/{milestone_id}", response_model=MilestoneOut)
def update_milestone_status(
    org_id: str, milestone_id: str, body: MilestoneStatusUpdate,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    item = db.query(Milestone).filter_by(id=milestone_id, org_id=org_id).first()
    if item is None:
        raise HTTPException(404, "Milestone not found")
    _write_access(org_id, p, db, item.workspace_id)
    item.status = body.status
    _event(db, org_id, p.user.id, "milestone.status_changed", "milestone",
           item.id, item.workspace_id, {"status": item.status})
    db.commit()
    db.refresh(item)
    return item
