"""Private AI business workflows: durable OS records, no model/runtime ownership."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session
from app.auth import Principal, get_principal, has_founder_authority, require_membership, require_workspace_access_from_context
from app.db import get_db
from app.data_protection import DataProtectionBlocked, sanitize_text, protect_untrusted_payload
from app.audit import record_event
from app.models import Role, Approval, Workspace
from app.domain_models import Client, Lead, Opportunity, Project
from app.operations_models import Proposal, InvoiceRecord
from app.private_ops_models import KnowledgeItem, BusinessDraft

router = APIRouter(prefix="/v1/orgs/{org_id}", tags=["private-operations"])
WRITERS = {Role.owner, Role.admin, Role.operator}

def _access(db: Session, org_id: str, workspace_id: str, principal: Principal, write: bool = False) -> None:
    role = require_membership(org_id, principal, db)
    if write and role not in WRITERS and not has_founder_authority(db, org_id, principal.user.id):
        raise HTTPException(403, "Workspace writer role required")
    require_workspace_access_from_context(org_id, workspace_id, db)

def _safe(value: str, limit: int = 30000) -> str:
    try:
        clean, _ = sanitize_text(value)
    except DataProtectionBlocked as exc:
        raise HTTPException(422, "Content contains a prohibited secret or invalid data") from exc
    if len(clean) > limit: raise HTTPException(422, "Content exceeds the allowed length")
    return clean

class KnowledgeCreate(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=36)
    client_id: str | None = Field(default=None, max_length=36)
    key: str = Field(min_length=2, max_length=160, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._/-]*$")
    title: str = Field(min_length=2, max_length=240)
    content: str = Field(min_length=1, max_length=30000)
    source_type: str = Field(pattern=r"^(founder_note|document|meeting|project|crm|policy)$")
    source_reference: str = Field(min_length=2, max_length=240)
    classification: str = Field(default="internal", pattern=r"^(public|internal|confidential|restricted)$")
    effective_from: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    effective_until: datetime | None = None
    retention_policy: str = Field(default="standard", pattern=r"^(standard|contractual|legal_hold)$")
    retention_until: datetime | None = None

    @model_validator(mode="after")
    def validate_effective_window(self):
        if self.effective_from and self.effective_until and self.effective_until < self.effective_from:
            raise ValueError("effective_until must not precede effective_from")
        return self

class WorkspaceBody(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=36)

class DraftCreate(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=36)
    kind: str = Field(pattern=r"^(front_desk|meeting_proposal|receivable_followup)$")
    source_refs: list[dict] = Field(min_length=1, max_length=20)
    content: dict

class DraftReview(BaseModel):
    workspace_id: str
    decision: str = Field(pattern=r"^(reviewed|rejected)$")

def _knowledge_out(item):
    return {"id": item.id, "workspace_id": item.workspace_id, "key": item.key, "version": item.version,
        "title": item.title, "content": item.content, "source_type": item.source_type,
        "source_reference": item.source_reference, "classification": item.classification,
        "client_id": item.client_id, "owner_user_id": item.owner_user_id,
        "effective_from": item.effective_from, "effective_until": item.effective_until,
        "retention_policy": item.retention_policy, "retention_until": item.retention_until,
        "status": item.status, "supersedes_id": item.supersedes_id,
        "approved_by": item.approved_by, "approved_at": item.approved_at, "created_at": item.created_at}

@router.post("/knowledge", status_code=201)
def create_knowledge(body: KnowledgeCreate, org_id: str, db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    _access(db, org_id, body.workspace_id, p, write=True)
    if body.client_id and not db.query(Client.id).filter_by(id=body.client_id, org_id=org_id, workspace_id=body.workspace_id).first():
        raise HTTPException(404, "Client not found in this workspace")
    # Serialize version allocation on the workspace row so concurrent writers
    # cannot both allocate the same version for a key.
    db.query(Workspace).filter_by(id=body.workspace_id, org_id=org_id).with_for_update().first()
    latest = db.query(KnowledgeItem).filter_by(org_id=org_id, workspace_id=body.workspace_id, key=body.key).order_by(KnowledgeItem.version.desc()).first()
    item = KnowledgeItem(org_id=org_id, workspace_id=body.workspace_id, key=body.key,
        version=(latest.version + 1 if latest else 1), title=_safe(body.title, 240), content=_safe(body.content),
        source_type=body.source_type, source_reference=_safe(body.source_reference, 240),
        classification=body.classification, client_id=body.client_id, owner_user_id=p.user.id,
        effective_from=body.effective_from, effective_until=body.effective_until,
        retention_policy=body.retention_policy, retention_until=body.retention_until,
        supersedes_id=latest.id if latest else None, created_by=p.user.id)
    db.add(item); db.flush()
    record_event(db, org_id, p.user.id, "knowledge.version_created", "knowledge_item", item.id, body.workspace_id,
                 {"key": item.key, "version": item.version, "classification": item.classification})
    db.commit(); db.refresh(item)
    return _knowledge_out(item)

@router.get("/knowledge")
def list_knowledge(org_id: str, workspace_id: str = Query(min_length=1), key: str | None = None,
                   client_id: str | None = None, approved_only: bool = False,
                   db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    _access(db, org_id, workspace_id, p)
    query = db.query(KnowledgeItem).filter_by(org_id=org_id, workspace_id=workspace_id)
    if key: query = query.filter(KnowledgeItem.key == key)
    if client_id: query = query.filter(KnowledgeItem.client_id == client_id)
    if approved_only: query = query.filter(KnowledgeItem.status == "approved")
    return [_knowledge_out(x) for x in query.order_by(KnowledgeItem.key, KnowledgeItem.version.desc()).limit(500).all()]

@router.post("/knowledge/{item_id}/approve")
def approve_knowledge(item_id: str, body: WorkspaceBody, org_id: str, db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    _access(db, org_id, body.workspace_id, p, write=True)
    if not has_founder_authority(db, org_id, p.user.id):
        raise HTTPException(403, "Founder authority is required to approve canonical knowledge")
    item = db.query(KnowledgeItem).filter_by(id=item_id, org_id=org_id, workspace_id=body.workspace_id).with_for_update().first()
    if item is None: raise HTTPException(404, "Knowledge item not found")
    item.status, item.approved_by, item.approved_at = "approved", p.user.id, datetime.now(timezone.utc)
    record_event(db, org_id, p.user.id, "knowledge.approved", "knowledge_item", item.id, body.workspace_id, {"version": item.version})
    db.commit(); db.refresh(item)
    return _knowledge_out(item)

def _verify_sources(db: Session, org_id: str, workspace_id: str, refs: list[dict]) -> None:
    allowed = {"lead": Lead, "opportunity": Opportunity, "invoice": InvoiceRecord, "project": Project, "proposal": Proposal}
    for ref in refs:
        if set(ref) != {"type", "id"} or ref["type"] not in allowed or not isinstance(ref["id"], str):
            raise HTTPException(422, "Each source reference must contain a supported type and id")
        exists = db.query(allowed[ref["type"]].id).filter_by(id=ref["id"], org_id=org_id, workspace_id=workspace_id).first()
        if not exists: raise HTTPException(404, "A referenced source record was not found in this workspace")

def _draft_out(d):
    return {"id": d.id, "workspace_id": d.workspace_id, "kind": d.kind, "source_refs": d.source_refs,
        "content": d.content, "status": d.status, "reviewed_by": d.reviewed_by,
        "reviewed_at": d.reviewed_at, "created_at": d.created_at}

@router.post("/business-drafts", status_code=201)
def create_business_draft(body: DraftCreate, org_id: str, db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    _access(db, org_id, body.workspace_id, p, write=True)
    _verify_sources(db, org_id, body.workspace_id, body.source_refs)
    if body.kind == "front_desk" and not any(x["type"] == "lead" for x in body.source_refs):
        raise HTTPException(422, "Front-desk drafts must reference a lead")
    if body.kind == "meeting_proposal" and not any(x["type"] in {"opportunity", "project"} for x in body.source_refs):
        raise HTTPException(422, "Meeting-to-proposal drafts must reference an opportunity or project")
    if body.kind == "receivable_followup" and not any(x["type"] == "invoice" for x in body.source_refs):
        raise HTTPException(422, "Receivables drafts must reference an invoice")
    if any(not isinstance(key, str) or len(key) > 80 for key in body.content):
        raise HTTPException(422, "Draft content keys must be short strings")
    try:
        safe_content, _report = protect_untrusted_payload(body.content)
    except DataProtectionBlocked as exc:
        raise HTTPException(422, "Draft content contains prohibited or oversized data") from exc
    draft = BusinessDraft(org_id=org_id, workspace_id=body.workspace_id, kind=body.kind,
        source_refs=body.source_refs, content=safe_content, created_by=p.user.id)
    db.add(draft); db.flush()
    record_event(db, org_id, p.user.id, "business_draft.created", "business_draft", draft.id, body.workspace_id,
                 {"kind": draft.kind, "source_count": len(draft.source_refs)})
    db.commit(); db.refresh(draft)
    return _draft_out(draft)

@router.get("/business-drafts")
def list_business_drafts(org_id: str, workspace_id: str = Query(min_length=1), kind: str | None = None,
                         db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    _access(db, org_id, workspace_id, p)
    query = db.query(BusinessDraft).filter_by(org_id=org_id, workspace_id=workspace_id)
    if kind: query = query.filter(BusinessDraft.kind == kind)
    return [_draft_out(x) for x in query.order_by(BusinessDraft.created_at.desc()).limit(200).all()]

@router.post("/business-drafts/{draft_id}/review")
def review_business_draft(draft_id: str, body: DraftReview, org_id: str, db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    _access(db, org_id, body.workspace_id, p, write=True)
    draft = db.query(BusinessDraft).filter_by(id=draft_id, org_id=org_id, workspace_id=body.workspace_id).with_for_update().first()
    if draft is None: raise HTTPException(404, "Business draft not found")
    draft.status, draft.reviewed_by, draft.reviewed_at = body.decision, p.user.id, datetime.now(timezone.utc)
    record_event(db, org_id, p.user.id, f"business_draft.{body.decision}", "business_draft", draft.id, body.workspace_id, {"kind": draft.kind})
    db.commit(); db.refresh(draft)
    return _draft_out(draft)

@router.get("/receivables/aging")
def receivables_aging(org_id: str, workspace_id: str = Query(min_length=1), as_of: datetime | None = None,
                      db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    _access(db, org_id, workspace_id, p)
    now = as_of or datetime.now(timezone.utc)
    invoices = db.query(InvoiceRecord).filter(InvoiceRecord.org_id == org_id, InvoiceRecord.workspace_id == workspace_id,
        InvoiceRecord.status.in_(["issued", "partially_paid"])).all()
    bucket_names = ("current", "1_30", "31_60", "61_90", "over_90")
    buckets_by_currency: dict[str, dict[str, int]] = {}
    rows = []
    for inv in invoices:
        outstanding = inv.amount_minor - inv.paid_minor
        if outstanding <= 0: continue
        due = inv.due_date
        if due.tzinfo is None: due = due.replace(tzinfo=timezone.utc)
        days = max(0, (now - due).days)
        bucket = "current" if days == 0 else "1_30" if days <= 30 else "31_60" if days <= 60 else "61_90" if days <= 90 else "over_90"
        currency_buckets = buckets_by_currency.setdefault(inv.currency, {name: 0 for name in bucket_names})
        currency_buckets[bucket] += outstanding
        rows.append({"invoice_id": inv.id, "invoice_number": inv.invoice_number, "client_id": inv.client_id,
            "amount_minor": inv.amount_minor, "paid_minor": inv.paid_minor, "outstanding_minor": outstanding,
            "currency": inv.currency, "due_date": inv.due_date, "days_overdue": days, "bucket": bucket})
    return {"as_of": now, "currency_note": "Amounts remain grouped by invoice currency; do not sum across currencies.",
        "buckets_by_currency_minor": buckets_by_currency, "invoices": rows}

@router.get("/founder-brief")
def founder_brief(org_id: str, workspace_id: str = Query(min_length=1),
                  db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    _access(db, org_id, workspace_id, p)
    today = datetime.now(timezone.utc)
    overdue = db.query(InvoiceRecord).filter(InvoiceRecord.org_id == org_id, InvoiceRecord.workspace_id == workspace_id,
        InvoiceRecord.status.in_(["issued", "partially_paid"]), InvoiceRecord.due_date < today,
        InvoiceRecord.paid_minor < InvoiceRecord.amount_minor).count()
    return {"generated_at": today, "workspace_id": workspace_id,
        "signals": {
            "new_leads": db.query(Lead).filter_by(org_id=org_id, workspace_id=workspace_id, stage="new").count(),
            "open_opportunities": db.query(Opportunity).filter(Opportunity.org_id == org_id, Opportunity.workspace_id == workspace_id,
                Opportunity.stage.notin_(["won", "lost"])).count(),
            "proposals_pending": db.query(Proposal).filter_by(org_id=org_id, workspace_id=workspace_id, status="pending_approval").count(),
            "overdue_invoices": overdue,
            "active_projects": db.query(Project).filter(Project.org_id == org_id, Project.workspace_id == workspace_id,
                Project.status.in_(["active", "in_progress"])).count(),
            "pending_approvals": db.query(Approval).filter_by(org_id=org_id, workspace_id=workspace_id, status="pending").count(),
        },
        "note": "Read-only operational count snapshot. Open the corresponding OS modules for source records; no model-generated claims or external actions are performed."}
