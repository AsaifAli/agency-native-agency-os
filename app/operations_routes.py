"""Workspace-scoped delivery operations and commercial controls.

These endpoints persist operational records. They do not send invoices, collect
payments, authorize scope changes without a founder approval, or dispatch events.
"""
from datetime import datetime, timedelta, timezone
import uuid
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import (
    Principal, get_principal, has_founder_authority, require_founder_authority,
    require_membership, require_role,
)
from app.db import get_db
from app.models import Role, Workspace, Approval, ApprovalStatus, Execution, ExecutionStatus, Task, Agent

from app.domain_models import Project, Opportunity, Client
from app.operations_models import ServicePlaybook, ServiceOffering, Proposal, ContractRecord, ClientOnboarding, OnboardingChecklistItem, InvoiceRecord, PaymentReceipt, ScopeChangeRequest, TimeEntry, ProjectCost
from app.telephony.models import OutboxEvent
from app.action_policy import require_approved_action
from app.audit import record_event

router = APIRouter(prefix="/v1/orgs/{org_id}/operations", tags=["delivery-operations"])
WRITERS = {Role.owner, Role.admin, Role.operator}


def _workspace(db: Session, org_id: str, workspace_id: str) -> None:
    if not db.query(Workspace.id).filter_by(id=workspace_id, org_id=org_id).first():
        raise HTTPException(404, "Workspace not found")


def _project(db: Session, org_id: str, workspace_id: str, project_id: str) -> Project:
    item = db.query(Project).filter_by(
        id=project_id, org_id=org_id, workspace_id=workspace_id
    ).first()
    if item is None:
        raise HTTPException(404, "Project not found")
    return item


def _write(org_id: str, workspace_id: str, p: Principal, db: Session) -> None:
    role = require_membership(org_id, p, db)
    if role not in WRITERS and not has_founder_authority(db, org_id, p.user.id):
        require_role(role, WRITERS)
    _workspace(db, org_id, workspace_id)


def _write_or_founder(org_id: str, workspace_id: str, p: Principal, db: Session) -> None:
    _write(org_id, workspace_id, p, db)


def _read_or_founder(
    org_id: str, workspace_id: str, p: Principal, db: Session, roles: set[Role],
) -> None:
    role = require_membership(org_id, p, db)
    if role not in roles and not has_founder_authority(db, org_id, p.user.id):
        require_role(role, roles)
    _workspace(db, org_id, workspace_id)


def _event(db, org_id, actor_id, event_type, resource_type, resource_id, workspace_id, payload=None):
    record_event(db, org_id, actor_id, event_type, resource_type, resource_id, workspace_id, payload or {})


def _outbox(db, org_id, workspace_id, event_type, aggregate_type, aggregate_id, payload, key_suffix=None):
    key = f"{event_type}:{aggregate_id}:{key_suffix}" if key_suffix else f"{event_type}:{aggregate_id}"
    db.add(OutboxEvent(
        org_id=org_id, workspace_id=workspace_id, event_type=event_type,
        schema_version=1, aggregate_type=aggregate_type, aggregate_id=aggregate_id,
        idempotency_key=key, payload=payload,
    ))


class PlaybookCreate(BaseModel):
    workspace_id: str
    title: str = Field(min_length=2, max_length=200)
    service_line: str = Field(min_length=2, max_length=80)
    workflow: dict = Field(default_factory=dict)
    required_inputs: list[str] = Field(default_factory=list, max_length=100)
    deliverables: list[str] = Field(default_factory=list, max_length=100)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=100)
    security_checks: list[str] = Field(default_factory=list, max_length=100)


class PlaybookStatusUpdate(BaseModel):
    status: str = Field(pattern="^(draft|active|retired)$")


class PlaybookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workspace_id: str
    title: str
    service_line: str
    version: int
    status: str
    workflow: dict
    required_inputs: list
    deliverables: list
    acceptance_criteria: list
    security_checks: list
    created_at: datetime
    updated_at: datetime


class ServiceOfferingCreate(BaseModel):
    workspace_id: str
    code: str = Field(pattern="^[a-z0-9][a-z0-9_-]{1,59}$")
    name: str = Field(min_length=2, max_length=200)
    service_line: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=10, max_length=8000)
    pricing_model: str = Field(pattern="^(fixed|hourly|retainer|custom)$")
    indicative_price_minor: int | None = Field(default=None, ge=0, le=2_000_000_000)
    currency: str = Field(default="INR", pattern="^[A-Z]{3}$")
    typical_duration_days: int = Field(default=0, ge=0, le=3650)
    target_outcomes: list[str] = Field(default_factory=list, max_length=50)
    deliverables: list[str] = Field(default_factory=list, max_length=100)
    required_inputs: list[str] = Field(default_factory=list, max_length=100)
    exclusions: list[str] = Field(default_factory=list, max_length=100)
    notes: str = Field(default="", max_length=8000)


class ServiceOfferingStatusUpdate(BaseModel):
    status: str = Field(pattern="^(active|retired)$")


class ServiceOfferingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workspace_id: str
    code: str
    name: str
    service_line: str
    description: str
    pricing_model: str
    indicative_price_minor: int | None
    currency: str
    typical_duration_days: int
    target_outcomes: list
    deliverables: list
    required_inputs: list
    exclusions: list
    notes: str
    version: int
    status: str
    created_at: datetime
    updated_at: datetime


class InvoiceLineItem(BaseModel):
    description: str = Field(min_length=2, max_length=500)
    amount_minor: int = Field(gt=0, le=2_000_000_000)


class InvoiceCreate(BaseModel):
    workspace_id: str
    contract_id: str
    project_id: str | None = None
    invoice_number: str = Field(pattern="^[A-Za-z0-9][A-Za-z0-9._/-]{1,79}$")
    title: str = Field(min_length=3, max_length=240)
    description: str = Field(default="", max_length=8000)
    line_items: list[InvoiceLineItem] = Field(min_length=1, max_length=50)
    due_date: datetime


class InvoiceIssueEvidence(BaseModel):
    approval_id: str = Field(min_length=1, max_length=36)
    external_reference: str = Field(min_length=3, max_length=240)
    issued_at: datetime


class PaymentReceiptCreate(BaseModel):
    external_reference: str = Field(min_length=3, max_length=240)
    amount_minor: int = Field(gt=0, le=2_000_000_000)
    payment_method: str = Field(pattern="^(bank_transfer|cash|card|upi|cheque|other)$")
    source: str = Field(min_length=2, max_length=80)
    paid_at: datetime
    notes: str = Field(default="", max_length=2000)


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workspace_id: str
    client_id: str
    contract_id: str
    project_id: str | None
    invoice_number: str
    title: str
    description: str
    line_items: list
    amount_minor: int
    paid_minor: int
    outstanding_minor: int
    currency: str
    due_date: datetime
    status: str
    approval_id: str | None
    external_reference: str
    issued_at: datetime | None
    issued_by: str | None
    created_by: str
    created_at: datetime
    updated_at: datetime


class PaymentReceiptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    invoice_id: str
    external_reference: str
    amount_minor: int
    currency: str
    payment_method: str
    source: str
    paid_at: datetime
    notes: str
    recorded_by: str
    created_at: datetime


class OnboardingCreate(BaseModel):
    workspace_id: str
    contract_id: str


class OnboardingItemUpdate(BaseModel):
    status: str = Field(pattern="^(open|completed|waived)$")
    note: str = Field(default="", max_length=2000)


class OnboardingActivationPlan(BaseModel):
    project_name: str = Field(min_length=3, max_length=240)
    budget_minor: int = Field(ge=0, le=2_000_000_000)
    estimated_hours: int = Field(ge=0, le=100000)
    due_date: datetime | None = None


class OnboardingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workspace_id: str
    client_id: str
    contract_id: str
    project_id: str | None
    status: str
    approval_id: str | None
    project_name: str
    budget_minor: int
    estimated_hours: int
    due_date: datetime | None
    activated_by: str | None
    activated_at: datetime | None
    created_by: str
    created_at: datetime


class OnboardingItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    onboarding_id: str
    code: str
    title: str
    description: str
    required: bool
    status: str
    completion_note: str
    completed_by: str | None
    completed_at: datetime | None
    waived_by: str | None
    waived_at: datetime | None


class ContractCreate(BaseModel):
    workspace_id: str
    proposal_id: str
    contract_number: str = Field(pattern="^[A-Za-z0-9][A-Za-z0-9._/-]{1,79}$")
    title: str = Field(min_length=3, max_length=240)


class ContractExecutionEvidence(BaseModel):
    approval_id: str = Field(min_length=1, max_length=36)
    signed_reference: str = Field(min_length=3, max_length=240)
    signed_at: datetime


class ContractReject(BaseModel):
    approval_id: str = Field(min_length=1, max_length=36)
    note: str = Field(min_length=3, max_length=2000)


class ContractOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workspace_id: str
    client_id: str
    proposal_id: str
    contract_number: str
    title: str
    amount_minor: int
    currency: str
    terms_snapshot: dict
    status: str
    approval_id: str | None
    signed_reference: str
    signed_at: datetime | None
    executed_by: str | None
    executed_at: datetime | None
    created_by: str
    created_at: datetime
    updated_at: datetime


class ProposalCreate(BaseModel):
    workspace_id: str
    opportunity_id: str
    title: str = Field(min_length=3, max_length=240)
    service_line: str = Field(min_length=2, max_length=120)
    scope_summary: str = Field(min_length=10, max_length=12000)
    deliverables: list[str] = Field(default_factory=list, max_length=100)
    assumptions: list[str] = Field(default_factory=list, max_length=100)
    exclusions: list[str] = Field(default_factory=list, max_length=100)
    amount_minor: int = Field(ge=0, le=2_000_000_000)
    currency: str = Field(pattern="^[A-Z]{3}$")
    validity_days: int = Field(default=30, ge=1, le=180)


class ProposalDecision(BaseModel):
    approval_id: str = Field(min_length=1, max_length=36)
    note: str = Field(default="", max_length=2000)


class ProposalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workspace_id: str
    opportunity_id: str
    title: str
    service_line: str
    scope_summary: str
    deliverables: list
    assumptions: list
    exclusions: list
    amount_minor: int
    currency: str
    validity_days: int
    status: str
    approval_id: str | None
    approved_by: str | None
    approved_at: datetime | None
    created_by: str
    created_at: datetime
    updated_at: datetime


class ScopeChangeCreate(BaseModel):
    workspace_id: str
    project_id: str
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(default="", max_length=12000)
    impact_summary: str = Field(default="", max_length=12000)
    estimated_hours_delta: int = Field(default=0, ge=-100000, le=100000)
    budget_delta_minor: int = Field(default=0, ge=-2_000_000_000, le=2_000_000_000)
    contract_value_delta_minor: int = Field(default=0, ge=-2_000_000_000, le=2_000_000_000)
    schedule_days_delta: int = Field(default=0, ge=-3650, le=3650)


class ScopeChangeApproval(BaseModel):
    approval_id: str = Field(min_length=1, max_length=36)


class ScopeChangeReject(BaseModel):
    note: str = Field(default="", max_length=2000)


class ScopeChangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workspace_id: str
    project_id: str
    title: str
    description: str
    impact_summary: str
    estimated_hours_delta: int
    budget_delta_minor: int
    contract_value_delta_minor: int
    schedule_days_delta: int
    status: str
    requested_by: str
    decided_by: str | None
    approval_id: str | None
    created_at: datetime
    decided_at: datetime | None


class TimeEntryCreate(BaseModel):
    workspace_id: str
    project_id: str
    task_id: str | None = None
    description: str = Field(min_length=2, max_length=500)
    duration_minutes: int = Field(gt=0, le=1440)
    billable: bool = True
    hourly_cost_minor: int = Field(default=0, ge=0, le=100_000_000)
    started_at: datetime


class TimeEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workspace_id: str
    project_id: str
    task_id: str | None
    user_id: str
    description: str
    duration_minutes: int
    billable: bool
    hourly_cost_minor: int
    started_at: datetime
    created_at: datetime


class ProjectCostCreate(BaseModel):
    workspace_id: str
    project_id: str
    category: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=2, max_length=500)
    amount_minor: int = Field(ge=0, le=2_000_000_000)
    currency: str = Field(pattern="^[A-Z]{3}$")
    incurred_at: datetime


class ProjectCostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workspace_id: str
    project_id: str
    category: str
    description: str
    amount_minor: int
    currency: str
    incurred_at: datetime
    recorded_by: str
    created_at: datetime


@router.get("/service-catalog", response_model=list[ServiceOfferingOut])
def list_service_offerings(
    org_id: str, workspace_id: str = Query(min_length=1), status: str | None = None,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    _read_or_founder(org_id, workspace_id, p, db, {Role.owner, Role.admin, Role.operator, Role.reviewer})
    query = db.query(ServiceOffering).filter_by(org_id=org_id, workspace_id=workspace_id)
    if status:
        if status not in {"draft", "active", "retired"}:
            raise HTTPException(422, "Unsupported service offering status")
        query = query.filter_by(status=status)
    return query.order_by(ServiceOffering.updated_at.desc(), ServiceOffering.name.asc()).limit(250).all()


@router.post("/service-catalog", response_model=ServiceOfferingOut, status_code=201)
def create_service_offering(
    org_id: str, body: ServiceOfferingCreate,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    _write(org_id, body.workspace_id, p, db)
    if body.pricing_model == "fixed" and body.indicative_price_minor is None:
        raise HTTPException(422, "Fixed-price offerings require an indicative price")
    code = body.code.lower().strip()
    latest = db.query(ServiceOffering).filter_by(
        org_id=org_id, workspace_id=body.workspace_id, code=code,
    ).order_by(ServiceOffering.version.desc()).first()
    if latest and latest.status != "retired":
        raise HTTPException(409, "Retire the current service offering before creating a new revision")
    next_version = latest.version + 1 if latest else 1
    item = ServiceOffering(
        org_id=org_id, workspace_id=body.workspace_id, code=code,
        name=body.name.strip(), service_line=body.service_line.strip(),
        description=body.description.strip(), pricing_model=body.pricing_model,
        indicative_price_minor=body.indicative_price_minor, currency=body.currency,
        typical_duration_days=body.typical_duration_days,
        target_outcomes=body.target_outcomes, deliverables=body.deliverables,
        required_inputs=body.required_inputs, exclusions=body.exclusions,
        notes=body.notes, version=next_version, created_by=p.user.id,
    )
    db.add(item)
    db.flush()
    _event(db, org_id, p.user.id, "commercial.service_offering_created", "service_offering", item.id,
           body.workspace_id, {"code": item.code, "pricing_model": item.pricing_model})
    _outbox(db, org_id, body.workspace_id, "commercial.service_offering_created", "service_offering", item.id,
            {"code": item.code})
    db.commit()
    db.refresh(item)
    return item


@router.patch("/service-catalog/{offering_id}/status", response_model=ServiceOfferingOut)
def update_service_offering_status(
    org_id: str, offering_id: str, body: ServiceOfferingStatusUpdate,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    item = db.query(ServiceOffering).filter_by(id=offering_id, org_id=org_id).with_for_update().first()
    if item is None:
        raise HTTPException(404, "Service offering not found")
    _write(org_id, item.workspace_id, p, db)
    require_founder_authority(db, org_id, p.user.id)
    if item.status == body.status:
        return item
    item.status = body.status
    event_type = f"commercial.service_offering_{body.status}"
    _event(db, org_id, p.user.id, event_type, "service_offering", item.id,
           item.workspace_id, {"status": item.status, "version": item.version})
    _outbox(db, org_id, item.workspace_id, event_type, "service_offering", item.id,
            {"status": item.status, "version": item.version})
    db.commit()
    db.refresh(item)
    return item


@router.get("/playbooks", response_model=list[PlaybookOut])
def list_playbooks(
    org_id: str, workspace_id: str = Query(min_length=1), status: str | None = None,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    require_membership(org_id, p, db)
    _workspace(db, org_id, workspace_id)
    q = db.query(ServicePlaybook).filter_by(org_id=org_id, workspace_id=workspace_id)
    if status:
        q = q.filter_by(status=status)
    return q.order_by(ServicePlaybook.updated_at.desc()).limit(250).all()


@router.post("/playbooks", response_model=PlaybookOut, status_code=201)
def create_playbook(
    org_id: str, body: PlaybookCreate,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    _write(org_id, body.workspace_id, p, db)
    item = ServicePlaybook(
        org_id=org_id, workspace_id=body.workspace_id, title=body.title,
        service_line=body.service_line, workflow=body.workflow,
        required_inputs=body.required_inputs, deliverables=body.deliverables,
        acceptance_criteria=body.acceptance_criteria,
        security_checks=body.security_checks, created_by=p.user.id,
    )
    db.add(item)
    db.flush()
    _event(db, org_id, p.user.id, "playbook.created", "service_playbook", item.id, body.workspace_id)
    _outbox(db, org_id, body.workspace_id, "operations.playbook_created", "service_playbook", item.id, {"service_line": item.service_line})
    db.commit()
    db.refresh(item)
    return item


@router.patch("/playbooks/{playbook_id}/status", response_model=PlaybookOut)
def update_playbook_status(
    org_id: str, playbook_id: str, body: PlaybookStatusUpdate,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    item = db.query(ServicePlaybook).filter_by(id=playbook_id, org_id=org_id).first()
    if item is None:
        raise HTTPException(404, "Playbook not found")
    _write(org_id, item.workspace_id, p, db)
    if body.status in {"active", "retired"}:
        require_founder_authority(db, org_id, p.user.id)
    item.status = body.status
    item.version += 1
    _event(db, org_id, p.user.id, "playbook.status_changed", "service_playbook", item.id, item.workspace_id, {"status": item.status})
    db.commit()
    db.refresh(item)
    return item


@router.get("/invoices", response_model=list[InvoiceOut])
def list_invoices(
    org_id: str, workspace_id: str = Query(min_length=1), status: str | None = None,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    _read_or_founder(org_id, workspace_id, p, db, {Role.owner, Role.admin, Role.operator, Role.reviewer})
    query = db.query(InvoiceRecord).filter_by(org_id=org_id, workspace_id=workspace_id)
    if status:
        if status not in {"draft", "pending_approval", "issued", "partially_paid", "paid", "rejected", "cancelled"}:
            raise HTTPException(422, "Unsupported invoice status")
        query = query.filter_by(status=status)
    return query.order_by(InvoiceRecord.created_at.desc()).limit(250).all()


@router.post("/invoices", response_model=InvoiceOut, status_code=201)
def create_invoice_draft(
    org_id: str, body: InvoiceCreate,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    _write(org_id, body.workspace_id, p, db)
    contract = db.query(ContractRecord).filter_by(
        id=body.contract_id, org_id=org_id, workspace_id=body.workspace_id, status="executed",
    ).with_for_update().first()
    if contract is None:
        raise HTTPException(409, "Invoice drafts require an executed contract in this workspace")
    if body.due_date.tzinfo is None:
        raise HTTPException(422, "Invoice due date must include a timezone")
    project_id = body.project_id
    if project_id:
        project = db.query(Project).filter_by(
            id=project_id, org_id=org_id, workspace_id=body.workspace_id,
            client_id=contract.client_id,
        ).first()
        if project is None:
            raise HTTPException(404, "Project not found for this contract client")
        onboarding = db.query(ClientOnboarding.id).filter_by(
            org_id=org_id, workspace_id=body.workspace_id,
            contract_id=contract.id, project_id=project.id, status="active",
        ).first()
        if onboarding is None:
            raise HTTPException(422, "Project is not linked through the executed contract onboarding")
    amount_minor = sum(line.amount_minor for line in body.line_items)
    billed = db.query(func.coalesce(func.sum(InvoiceRecord.amount_minor), 0)).filter(
        InvoiceRecord.org_id == org_id,
        InvoiceRecord.workspace_id == body.workspace_id,
        InvoiceRecord.contract_id == contract.id,
        InvoiceRecord.status.notin_(["rejected", "cancelled"]),
    ).scalar() or 0
    if amount_minor > contract.amount_minor - billed:
        raise HTTPException(422, "Invoice amount exceeds the unbilled executed contract value")
    duplicate = db.query(InvoiceRecord.id).filter_by(
        org_id=org_id, workspace_id=body.workspace_id, invoice_number=body.invoice_number.strip(),
    ).first()
    if duplicate:
        raise HTTPException(409, "Invoice number already exists in this workspace")
    item = InvoiceRecord(
        org_id=org_id, workspace_id=body.workspace_id, client_id=contract.client_id,
        contract_id=contract.id, project_id=project_id,
        invoice_number=body.invoice_number.strip(), title=body.title.strip(),
        description=body.description.strip(),
        line_items=[line.model_dump() for line in body.line_items],
        amount_minor=amount_minor, currency=contract.currency, due_date=body.due_date,
        created_by=p.user.id,
    )
    db.add(item)
    db.flush()
    _event(db, org_id, p.user.id, "finance.invoice_drafted", "invoice", item.id,
           body.workspace_id, {"contract_id": contract.id, "amount_minor": amount_minor, "currency": contract.currency})
    _outbox(db, org_id, body.workspace_id, "finance.invoice_drafted", "invoice", item.id,
            {"contract_id": contract.id, "amount_minor": amount_minor})
    db.commit()
    db.refresh(item)
    return item


@router.post("/invoices/{invoice_id}/submit-for-approval", response_model=InvoiceOut)
def submit_invoice_for_approval(
    org_id: str, invoice_id: str,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    item = db.query(InvoiceRecord).filter_by(id=invoice_id, org_id=org_id).with_for_update().first()
    if item is None:
        raise HTTPException(404, "Invoice not found")
    _write(org_id, item.workspace_id, p, db)
    if item.status == "pending_approval":
        return item
    if item.status not in {"draft", "rejected"}:
        raise HTTPException(409, "Only draft or rejected invoices can be submitted")
    approval = Approval(
        org_id=org_id, workspace_id=item.workspace_id, action_type="invoice.issue",
        resource_id=item.id, idempotency_key=f"invoice-issue:{item.id}:{uuid.uuid4()}",
        request_payload={
            "invoice_number": item.invoice_number, "contract_id": item.contract_id,
            "amount_minor": item.amount_minor, "currency": item.currency,
            "client_id": item.client_id, "due_date": item.due_date.isoformat(),
        },
        requested_by=p.user.id,
    )
    db.add(approval)
    db.flush()
    item.status = "pending_approval"
    item.approval_id = approval.id
    _event(db, org_id, p.user.id, "finance.invoice_submitted", "invoice", item.id,
           item.workspace_id, {"approval_id": approval.id, "action_type": "invoice.issue"})
    _outbox(db, org_id, item.workspace_id, "finance.invoice_submitted", "invoice", item.id,
            {"approval_id": approval.id}, key_suffix=approval.id)
    db.commit()
    db.refresh(item)
    return item


@router.post("/invoices/{invoice_id}/record-issued", response_model=InvoiceOut)
def record_invoice_issued(
    org_id: str, invoice_id: str, body: InvoiceIssueEvidence,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    item = db.query(InvoiceRecord).filter_by(id=invoice_id, org_id=org_id).with_for_update().first()
    if item is None:
        raise HTTPException(404, "Invoice not found")
    _write_or_founder(org_id, item.workspace_id, p, db)
    if item.status != "pending_approval" or item.approval_id != body.approval_id:
        raise HTTPException(409, "Invoice is not awaiting this approval")
    if body.issued_at.tzinfo is None or body.issued_at > datetime.now(timezone.utc):
        raise HTTPException(422, "Invoice issue timestamp must be timezone-aware and cannot be in the future")
    if len(body.external_reference.strip()) < 3:
        raise HTTPException(422, "External invoice reference must be non-empty")
    duplicate_reference = db.query(InvoiceRecord.id).filter(
        InvoiceRecord.org_id == org_id,
        InvoiceRecord.workspace_id == item.workspace_id,
        InvoiceRecord.external_reference == body.external_reference.strip(),
        InvoiceRecord.id != item.id,
        InvoiceRecord.external_reference != "",
    ).first()
    if duplicate_reference:
        raise HTTPException(409, "External invoice reference already belongs to another invoice")
    require_approved_action(
        db, approval_id=body.approval_id, org_id=org_id,
        workspace_id=item.workspace_id, action_type="invoice.issue",
        resource_id=item.id, actor_user_id=p.user.id,
    )
    item.status = "issued"
    item.external_reference = body.external_reference.strip()
    item.issued_at = body.issued_at
    item.issued_by = p.user.id
    _event(db, org_id, p.user.id, "finance.invoice_issued_recorded", "invoice", item.id,
           item.workspace_id, {"approval_id": body.approval_id, "external_reference": item.external_reference})
    _outbox(db, org_id, item.workspace_id, "finance.invoice_issued_recorded", "invoice", item.id,
            {"approval_id": body.approval_id})
    db.commit()
    db.refresh(item)
    return item


@router.post("/invoices/{invoice_id}/reject", response_model=InvoiceOut)
def reject_invoice(
    org_id: str, invoice_id: str, body: ContractReject,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    item = db.query(InvoiceRecord).filter_by(id=invoice_id, org_id=org_id).with_for_update().first()
    if item is None:
        raise HTTPException(404, "Invoice not found")
    require_founder_authority(db, org_id, p.user.id)
    if item.status != "pending_approval" or item.approval_id != body.approval_id:
        raise HTTPException(409, "Invoice is not awaiting this approval")
    approval = db.query(Approval).filter_by(
        id=body.approval_id, org_id=org_id, workspace_id=item.workspace_id,
        action_type="invoice.issue", resource_id=item.id,
    ).with_for_update().first()
    if approval is None:
        raise HTTPException(404, "Invoice approval not found")
    if approval.status == ApprovalStatus.pending:
        approval.status = ApprovalStatus.rejected
        approval.decided_by = p.user.id
        approval.decision_note = body.note
        approval.decided_at = datetime.now(timezone.utc)
    elif approval.status != ApprovalStatus.rejected or not approval.decided_by or not has_founder_authority(db, org_id, approval.decided_by):
        raise HTTPException(409, "Invoice approval is no longer rejectable")
    item.status = "rejected"
    _event(db, org_id, p.user.id, "finance.invoice_rejected", "invoice", item.id,
           item.workspace_id, {"approval_id": approval.id})
    db.commit()
    db.refresh(item)
    return item


@router.get("/invoices/{invoice_id}/payments", response_model=list[PaymentReceiptOut])
def list_invoice_payments(
    org_id: str, invoice_id: str,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    item = db.query(InvoiceRecord).filter_by(id=invoice_id, org_id=org_id).first()
    if item is None:
        raise HTTPException(404, "Invoice not found")
    require_membership(org_id, p, db)
    _workspace(db, org_id, item.workspace_id)
    return (db.query(PaymentReceipt).filter_by(
        org_id=org_id, workspace_id=item.workspace_id, invoice_id=item.id,
    ).order_by(PaymentReceipt.paid_at.asc()).limit(500).all())


@router.post("/invoices/{invoice_id}/payments", response_model=PaymentReceiptOut, status_code=201)
def record_payment_receipt(
    org_id: str, invoice_id: str, body: PaymentReceiptCreate,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    item = db.query(InvoiceRecord).filter_by(id=invoice_id, org_id=org_id).with_for_update().first()
    if item is None:
        raise HTTPException(404, "Invoice not found")
    _write(org_id, item.workspace_id, p, db)
    if item.status not in {"issued", "partially_paid"}:
        raise HTTPException(409, "Payments can only be reconciled against an issued, unpaid invoice")
    if body.paid_at.tzinfo is None or body.paid_at > datetime.now(timezone.utc):
        raise HTTPException(422, "Payment timestamp must be timezone-aware and cannot be in the future")
    if body.amount_minor > item.amount_minor - item.paid_minor:
        raise HTTPException(422, "Payment exceeds the invoice outstanding balance")
    reference = body.external_reference.strip()
    if len(reference) < 3 or len(body.source.strip()) < 2:
        raise HTTPException(422, "Payment reference and source must be non-empty")
    duplicate = db.query(PaymentReceipt.id).filter_by(
        org_id=org_id, workspace_id=item.workspace_id, external_reference=reference,
    ).first()
    if duplicate:
        raise HTTPException(409, "Payment reference already reconciled in this workspace")
    receipt = PaymentReceipt(
        org_id=org_id, workspace_id=item.workspace_id, invoice_id=item.id,
        external_reference=reference, amount_minor=body.amount_minor,
        currency=item.currency, payment_method=body.payment_method,
        source=body.source.strip(), paid_at=body.paid_at,
        notes=body.notes.strip(), recorded_by=p.user.id,
    )
    db.add(receipt)
    item.paid_minor += body.amount_minor
    item.status = "paid" if item.paid_minor == item.amount_minor else "partially_paid"
    db.flush()
    _event(db, org_id, p.user.id, "finance.payment_receipt_recorded", "payment_receipt", receipt.id,
           item.workspace_id, {"invoice_id": item.id, "amount_minor": receipt.amount_minor, "currency": receipt.currency})
    _outbox(db, org_id, item.workspace_id, "finance.payment_receipt_recorded", "payment_receipt", receipt.id,
            {"invoice_id": item.id, "amount_minor": receipt.amount_minor})
    db.commit()
    db.refresh(receipt)
    return receipt


@router.get("/onboardings", response_model=list[OnboardingOut])
def list_onboardings(
    org_id: str, workspace_id: str = Query(min_length=1),
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    _read_or_founder(org_id, workspace_id, p, db, {Role.owner, Role.admin, Role.operator, Role.reviewer})
    return (db.query(ClientOnboarding)
            .filter_by(org_id=org_id, workspace_id=workspace_id)
            .order_by(ClientOnboarding.created_at.desc()).limit(250).all())


@router.post("/onboardings", response_model=OnboardingOut, status_code=201)
def create_onboarding(
    org_id: str, body: OnboardingCreate,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    _write(org_id, body.workspace_id, p, db)
    contract = db.query(ContractRecord).filter_by(
        id=body.contract_id, org_id=org_id, workspace_id=body.workspace_id,
    ).first()
    if contract is None:
        raise HTTPException(404, "Contract not found")
    if contract.status != "executed":
        raise HTTPException(409, "Client onboarding requires a recorded executed contract")
    existing = db.query(ClientOnboarding.id).filter_by(
        org_id=org_id, workspace_id=body.workspace_id, contract_id=contract.id,
    ).first()
    if existing:
        raise HTTPException(409, "Onboarding already exists for this contract")
    item = ClientOnboarding(
        org_id=org_id, workspace_id=body.workspace_id, client_id=contract.client_id,
        contract_id=contract.id, created_by=p.user.id,
    )
    db.add(item)
    db.flush()
    checklist = [
        ("client_contacts", "Confirm client contacts and escalation path", "Record the primary sponsor, day-to-day contact and escalation route."),
        ("discovery_acceptance", "Confirm requirements and acceptance criteria", "Ensure discovery notes, scope boundaries and measurable acceptance criteria are agreed."),
        ("security_privacy", "Review data classification and security requirements", "Document data classes, workspace boundaries, access controls, retention and applicable client policies."),
        ("access_prerequisites", "Confirm access and delivery prerequisites", "Confirm required source-system access and approved secret-sharing route; never store credentials in checklist notes."),
        ("delivery_plan", "Agree delivery plan and change control", "Confirm delivery milestones, owners, dependencies, risks and the approved change-request process."),
        ("kickoff", "Schedule client kickoff", "Record the kickoff date, participants, agenda and communication cadence."),
    ]
    for code, title, description in checklist:
        db.add(OnboardingChecklistItem(
            org_id=org_id, workspace_id=body.workspace_id, onboarding_id=item.id,
            code=code, title=title, description=description, required=True,
        ))
    _event(db, org_id, p.user.id, "delivery.onboarding_created", "client_onboarding", item.id,
           body.workspace_id, {"contract_id": contract.id, "client_id": contract.client_id})
    _outbox(db, org_id, body.workspace_id, "delivery.onboarding_created", "client_onboarding", item.id,
            {"contract_id": contract.id, "client_id": contract.client_id})
    db.commit()
    db.refresh(item)
    return item


@router.get("/onboardings/{onboarding_id}/checklist", response_model=list[OnboardingItemOut])
def list_onboarding_checklist(
    org_id: str, onboarding_id: str,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    require_membership(org_id, p, db)
    item = db.query(ClientOnboarding).filter_by(id=onboarding_id, org_id=org_id).first()
    if item is None:
        raise HTTPException(404, "Onboarding not found")
    _workspace(db, org_id, item.workspace_id)
    return (db.query(OnboardingChecklistItem)
            .filter_by(org_id=org_id, workspace_id=item.workspace_id, onboarding_id=item.id)
            .order_by(OnboardingChecklistItem.created_at.asc()).all())


@router.patch("/onboardings/{onboarding_id}/checklist/{checklist_item_id}", response_model=OnboardingItemOut)
def update_onboarding_checklist_item(
    org_id: str, onboarding_id: str, checklist_item_id: str, body: OnboardingItemUpdate,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    onboarding = db.query(ClientOnboarding).filter_by(id=onboarding_id, org_id=org_id).with_for_update().first()
    if onboarding is None:
        raise HTTPException(404, "Onboarding not found")
    if body.status == "waived":
        _write_or_founder(org_id, onboarding.workspace_id, p, db)
    else:
        _write(org_id, onboarding.workspace_id, p, db)
    if onboarding.status != "preparing":
        raise HTTPException(409, "Checklist is locked after onboarding leaves preparation")
    item = db.query(OnboardingChecklistItem).filter_by(
        id=checklist_item_id, org_id=org_id, workspace_id=onboarding.workspace_id,
        onboarding_id=onboarding.id,
    ).with_for_update().first()
    if item is None:
        raise HTTPException(404, "Checklist item not found")
    if body.status == "waived":
        require_founder_authority(db, org_id, p.user.id)
        if len(body.note.strip()) < 3:
            raise HTTPException(422, "Founder waiver requires a reason")
        item.status = "waived"
        item.waived_by = p.user.id
        item.waived_at = datetime.now(timezone.utc)
        item.completed_by = None
        item.completed_at = None
        item.completion_note = body.note.strip()
    elif body.status == "completed":
        if len(body.note.strip()) < 3:
            raise HTTPException(422, "Checklist completion requires an evidence note")
        item.status = "completed"
        item.completed_by = p.user.id
        item.completed_at = datetime.now(timezone.utc)
        item.waived_by = None
        item.waived_at = None
        item.completion_note = body.note.strip()
    else:
        item.status = "open"
        item.completed_by = None
        item.completed_at = None
        item.waived_by = None
        item.waived_at = None
        item.completion_note = body.note.strip()
    _event(db, org_id, p.user.id, "delivery.onboarding_checklist_updated", "onboarding_checklist_item", item.id,
           onboarding.workspace_id, {"status": item.status, "required": item.required})
    db.commit()
    db.refresh(item)
    return item


@router.post("/onboardings/{onboarding_id}/submit-for-activation", response_model=OnboardingOut)
def submit_onboarding_for_activation(
    org_id: str, onboarding_id: str, body: OnboardingActivationPlan,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    item = db.query(ClientOnboarding).filter_by(id=onboarding_id, org_id=org_id).with_for_update().first()
    if item is None:
        raise HTTPException(404, "Onboarding not found")
    _write(org_id, item.workspace_id, p, db)
    if item.status != "preparing":
        raise HTTPException(409, "Only preparing onboarding can be submitted")
    open_required = db.query(OnboardingChecklistItem.id).filter_by(
        org_id=org_id, workspace_id=item.workspace_id, onboarding_id=item.id,
        required=True, status="open",
    ).first()
    if open_required:
        raise HTTPException(409, "Complete or explicitly waive all required checklist items before submission")
    contract = db.query(ContractRecord).filter_by(
        id=item.contract_id, org_id=org_id, workspace_id=item.workspace_id, status="executed",
    ).first()
    if contract is None:
        raise HTTPException(409, "Executed contract evidence is required")
    if body.due_date and body.due_date.tzinfo is None:
        raise HTTPException(422, "Project due date must include a timezone")
    approval = Approval(
        org_id=org_id, workspace_id=item.workspace_id, action_type="delivery.activate",
        resource_id=item.id, idempotency_key=f"delivery-activate:{item.id}:{uuid.uuid4()}",
        request_payload={
            "contract_id": contract.id, "client_id": item.client_id,
            "project_name": body.project_name, "budget_minor": body.budget_minor,
            "estimated_hours": body.estimated_hours,
            "due_date": body.due_date.isoformat() if body.due_date else None,
        },
        requested_by=p.user.id,
    )
    db.add(approval)
    db.flush()
    item.status = "pending_approval"
    item.approval_id = approval.id
    item.activation_plan = {
        "project_name": body.project_name, "budget_minor": body.budget_minor,
        "estimated_hours": body.estimated_hours,
        "due_date": body.due_date.isoformat() if body.due_date else None,
    }
    item.project_name = body.project_name
    item.budget_minor = body.budget_minor
    item.estimated_hours = body.estimated_hours
    item.due_date = body.due_date
    _event(db, org_id, p.user.id, "delivery.onboarding_submitted", "client_onboarding", item.id,
           item.workspace_id, {"approval_id": approval.id, "action_type": "delivery.activate"})
    _outbox(db, org_id, item.workspace_id, "delivery.onboarding_submitted", "client_onboarding", item.id,
            {"approval_id": approval.id}, key_suffix=approval.id)
    db.commit()
    db.refresh(item)
    return item


@router.post("/onboardings/{onboarding_id}/reject-activation", response_model=OnboardingOut)
def reject_onboarding_activation(
    org_id: str, onboarding_id: str, body: ContractReject,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    item = db.query(ClientOnboarding).filter_by(id=onboarding_id, org_id=org_id).with_for_update().first()
    if item is None:
        raise HTTPException(404, "Onboarding not found")
    require_founder_authority(db, org_id, p.user.id)
    if item.status != "pending_approval" or item.approval_id != body.approval_id:
        raise HTTPException(409, "Onboarding is not awaiting this approval")
    approval = db.query(Approval).filter_by(
        id=body.approval_id, org_id=org_id, workspace_id=item.workspace_id,
        action_type="delivery.activate", resource_id=item.id,
    ).with_for_update().first()
    if approval is None:
        raise HTTPException(404, "Delivery activation approval not found")
    if approval.status == ApprovalStatus.pending:
        approval.status = ApprovalStatus.rejected
        approval.decided_by = p.user.id
        approval.decision_note = body.note
        approval.decided_at = datetime.now(timezone.utc)
    elif approval.status != ApprovalStatus.rejected or not approval.decided_by or not has_founder_authority(db, org_id, approval.decided_by):
        raise HTTPException(409, "Delivery activation approval is no longer rejectable")
    item.status = "preparing"
    item.approval_id = None
    _event(db, org_id, p.user.id, "delivery.onboarding_activation_rejected", "client_onboarding", item.id,
           item.workspace_id, {"approval_id": approval.id, "note": body.note})
    db.commit()
    db.refresh(item)
    return item


@router.post("/onboardings/{onboarding_id}/activate", response_model=OnboardingOut)
def activate_onboarding(
    org_id: str, onboarding_id: str,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    item = db.query(ClientOnboarding).filter_by(id=onboarding_id, org_id=org_id).with_for_update().first()
    if item is None:
        raise HTTPException(404, "Onboarding not found")
    _write_or_founder(org_id, item.workspace_id, p, db)
    if item.status != "pending_approval" or not item.approval_id:
        raise HTTPException(409, "Onboarding is not awaiting delivery activation approval")
    contract = db.query(ContractRecord).filter_by(
        id=item.contract_id, org_id=org_id, workspace_id=item.workspace_id, status="executed",
    ).first()
    if contract is None:
        raise HTTPException(409, "Executed contract is no longer available")
    require_approved_action(
        db, approval_id=item.approval_id, org_id=org_id,
        workspace_id=item.workspace_id, action_type="delivery.activate",
        resource_id=item.id, actor_user_id=p.user.id,
    )
    proposal = db.query(Proposal).filter_by(
        id=contract.proposal_id, org_id=org_id, workspace_id=item.workspace_id,
    ).first()
    if proposal is None:
        raise HTTPException(409, "Contract proposal snapshot source is unavailable")
    project = Project(
        org_id=org_id, workspace_id=item.workspace_id, client_id=item.client_id,
        opportunity_id=proposal.opportunity_id, name=item.project_name,
        description=contract.terms_snapshot.get("scope_summary", ""),
        status="planned", priority="normal", budget_minor=item.budget_minor,
        contract_value_minor=contract.amount_minor, estimated_hours=item.estimated_hours,
        currency=contract.currency, due_date=item.due_date, owner_user_id=p.user.id,
    )
    db.add(project)
    db.flush()
    item.project_id = project.id
    item.status = "active"
    item.activated_by = p.user.id
    item.activated_at = datetime.now(timezone.utc)
    _event(db, org_id, p.user.id, "delivery.onboarding_activated", "client_onboarding", item.id,
           item.workspace_id, {"project_id": project.id, "contract_id": contract.id})
    _outbox(db, org_id, item.workspace_id, "delivery.onboarding_activated", "client_onboarding", item.id,
            {"project_id": project.id, "contract_id": contract.id})
    db.commit()
    db.refresh(item)
    return item


@router.get("/contracts", response_model=list[ContractOut])
def list_contracts(
    org_id: str, workspace_id: str = Query(min_length=1), status: str | None = None,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    _read_or_founder(org_id, workspace_id, p, db, {Role.owner, Role.admin, Role.operator, Role.reviewer})
    query = db.query(ContractRecord).filter_by(org_id=org_id, workspace_id=workspace_id)
    if status:
        if status not in {"draft", "pending_approval", "executed", "rejected", "terminated"}:
            raise HTTPException(422, "Unsupported contract status")
        query = query.filter_by(status=status)
    return query.order_by(ContractRecord.created_at.desc()).limit(250).all()


@router.post("/contracts", response_model=ContractOut, status_code=201)
def create_contract_draft(
    org_id: str, body: ContractCreate,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    _write(org_id, body.workspace_id, p, db)
    proposal = db.query(Proposal).filter_by(
        id=body.proposal_id, org_id=org_id, workspace_id=body.workspace_id,
    ).first()
    if proposal is None:
        raise HTTPException(404, "Proposal not found")
    if proposal.status != "approved" or not proposal.approval_id or not proposal.approved_by or not proposal.approved_at:
        raise HTTPException(409, "Only founder-approved proposals can enter the contract register")
    pricing_approval = db.query(Approval).filter_by(
        id=proposal.approval_id, org_id=org_id, workspace_id=body.workspace_id,
        action_type="pricing.change", resource_id=proposal.id,
        status=ApprovalStatus.approved,
    ).first()
    if (pricing_approval is None or pricing_approval.consumed_at is None
            or pricing_approval.consumed_by != proposal.approved_by
            or not has_founder_authority(db, org_id, proposal.approved_by)):
        raise HTTPException(409, "Proposal pricing approval evidence is incomplete or invalid")
    opportunity = db.query(Opportunity).filter_by(
        id=proposal.opportunity_id, org_id=org_id, workspace_id=body.workspace_id,
    ).first()
    if opportunity is None or not opportunity.client_id:
        raise HTTPException(422, "Link the opportunity to a client before drafting a contract")
    client = db.query(Client).filter_by(
        id=opportunity.client_id, org_id=org_id, workspace_id=body.workspace_id,
    ).first()
    if client is None:
        raise HTTPException(404, "Client not found in this workspace")
    duplicate = db.query(ContractRecord.id).filter_by(
        org_id=org_id, workspace_id=body.workspace_id, contract_number=body.contract_number.strip(),
    ).first()
    if duplicate:
        raise HTTPException(409, "Contract number already exists in this workspace")
    snapshot = {
        "proposal_id": proposal.id,
        "proposal_title": proposal.title,
        "service_line": proposal.service_line,
        "scope_summary": proposal.scope_summary,
        "deliverables": proposal.deliverables,
        "assumptions": proposal.assumptions,
        "exclusions": proposal.exclusions,
        "amount_minor": proposal.amount_minor,
        "currency": proposal.currency,
        "validity_days": proposal.validity_days,
        "proposal_approved_by": proposal.approved_by,
        "proposal_approved_at": proposal.approved_at.isoformat() if proposal.approved_at else None,
    }
    item = ContractRecord(
        org_id=org_id, workspace_id=body.workspace_id, client_id=client.id,
        proposal_id=proposal.id, contract_number=body.contract_number.strip(),
        title=body.title.strip(), amount_minor=proposal.amount_minor,
        currency=proposal.currency, terms_snapshot=snapshot, created_by=p.user.id,
    )
    db.add(item)
    db.flush()
    _event(db, org_id, p.user.id, "commercial.contract_drafted", "contract", item.id,
           body.workspace_id, {"proposal_id": proposal.id, "client_id": client.id, "contract_number": item.contract_number})
    _outbox(db, org_id, body.workspace_id, "commercial.contract_drafted", "contract", item.id,
            {"proposal_id": proposal.id, "client_id": client.id})
    db.commit()
    db.refresh(item)
    return item


@router.post("/contracts/{contract_id}/submit-for-approval", response_model=ContractOut)
def submit_contract_for_approval(
    org_id: str, contract_id: str,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    item = db.query(ContractRecord).filter_by(id=contract_id, org_id=org_id).with_for_update().first()
    if item is None:
        raise HTTPException(404, "Contract not found")
    _write(org_id, item.workspace_id, p, db)
    if item.status == "pending_approval":
        return item
    if item.status != "draft":
        raise HTTPException(409, "Only draft contracts can be submitted")
    approval = Approval(
        org_id=org_id, workspace_id=item.workspace_id, action_type="contract.execute",
        resource_id=item.id, idempotency_key=f"contract-execute:{item.id}",
        request_payload={
            "contract_number": item.contract_number, "title": item.title,
            "amount_minor": item.amount_minor, "currency": item.currency,
            "client_id": item.client_id, "proposal_id": item.proposal_id,
        },
        requested_by=p.user.id,
    )
    db.add(approval)
    db.flush()
    item.status = "pending_approval"
    item.approval_id = approval.id
    _event(db, org_id, p.user.id, "commercial.contract_submitted", "contract", item.id,
           item.workspace_id, {"approval_id": approval.id, "action_type": "contract.execute"})
    _outbox(db, org_id, item.workspace_id, "commercial.contract_submitted", "contract", item.id,
            {"approval_id": approval.id})
    db.commit()
    db.refresh(item)
    return item


@router.post("/contracts/{contract_id}/record-execution", response_model=ContractOut)
def record_contract_execution(
    org_id: str, contract_id: str, body: ContractExecutionEvidence,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    item = db.query(ContractRecord).filter_by(id=contract_id, org_id=org_id).with_for_update().first()
    if item is None:
        raise HTTPException(404, "Contract not found")
    require_founder_authority(db, org_id, p.user.id)
    if item.status != "pending_approval" or item.approval_id != body.approval_id:
        raise HTTPException(409, "Contract is not awaiting this approval")
    if body.signed_at.tzinfo is None:
        raise HTTPException(422, "Signed timestamp must include a timezone")
    if body.signed_at > datetime.now(timezone.utc):
        raise HTTPException(422, "Signed timestamp cannot be in the future")
    require_approved_action(
        db, approval_id=body.approval_id, org_id=org_id,
        workspace_id=item.workspace_id, action_type="contract.execute",
        resource_id=item.id, actor_user_id=p.user.id,
    )
    item.status = "executed"
    item.signed_reference = body.signed_reference.strip()
    item.signed_at = body.signed_at
    item.executed_by = p.user.id
    item.executed_at = datetime.now(timezone.utc)
    _event(db, org_id, p.user.id, "commercial.contract_execution_recorded", "contract", item.id,
           item.workspace_id, {"approval_id": body.approval_id, "signed_reference": item.signed_reference})
    _outbox(db, org_id, item.workspace_id, "commercial.contract_execution_recorded", "contract", item.id,
            {"approval_id": body.approval_id})
    db.commit()
    db.refresh(item)
    return item


@router.post("/contracts/{contract_id}/reject", response_model=ContractOut)
def reject_contract(
    org_id: str, contract_id: str, body: ContractReject,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    item = db.query(ContractRecord).filter_by(id=contract_id, org_id=org_id).with_for_update().first()
    if item is None:
        raise HTTPException(404, "Contract not found")
    require_founder_authority(db, org_id, p.user.id)
    if item.status != "pending_approval" or item.approval_id != body.approval_id:
        raise HTTPException(409, "Contract is not awaiting this approval")
    approval = db.query(Approval).filter_by(
        id=body.approval_id, org_id=org_id, workspace_id=item.workspace_id,
        action_type="contract.execute", resource_id=item.id,
    ).with_for_update().first()
    if approval is None:
        raise HTTPException(404, "Contract approval not found")
    if approval.status == ApprovalStatus.pending:
        approval.status = ApprovalStatus.rejected
        approval.decided_by = p.user.id
        approval.decision_note = body.note
        approval.decided_at = datetime.now(timezone.utc)
    elif approval.status != ApprovalStatus.rejected or not approval.decided_by or not has_founder_authority(db, org_id, approval.decided_by):
        raise HTTPException(409, "Contract approval is no longer rejectable")
    item.status = "rejected"
    _event(db, org_id, p.user.id, "commercial.contract_rejected", "contract", item.id,
           item.workspace_id, {"approval_id": body.approval_id})
    _outbox(db, org_id, item.workspace_id, "commercial.contract_rejected", "contract", item.id,
            {"approval_id": body.approval_id})
    db.commit()
    db.refresh(item)
    return item


@router.get("/proposals", response_model=list[ProposalOut])
def list_proposals(
    org_id: str, workspace_id: str = Query(min_length=1), opportunity_id: str | None = None,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    _read_or_founder(org_id, workspace_id, p, db, {Role.owner, Role.admin, Role.operator, Role.reviewer})
    query = db.query(Proposal).filter_by(org_id=org_id, workspace_id=workspace_id)
    if opportunity_id:
        opportunity = db.query(Opportunity).filter_by(
            id=opportunity_id, org_id=org_id, workspace_id=workspace_id
        ).first()
        if opportunity is None:
            raise HTTPException(404, "Opportunity not found")
        query = query.filter_by(opportunity_id=opportunity_id)
    return query.order_by(Proposal.created_at.desc()).limit(250).all()


@router.post("/proposals", response_model=ProposalOut, status_code=201)
def create_proposal(
    org_id: str, body: ProposalCreate,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    _write(org_id, body.workspace_id, p, db)
    opportunity = db.query(Opportunity).filter_by(
        id=body.opportunity_id, org_id=org_id, workspace_id=body.workspace_id
    ).first()
    if opportunity is None:
        raise HTTPException(404, "Opportunity not found")
    if body.currency != opportunity.currency:
        raise HTTPException(422, "Proposal currency must match the linked opportunity currency")
    item = Proposal(
        org_id=org_id, workspace_id=body.workspace_id, opportunity_id=body.opportunity_id,
        title=body.title, service_line=body.service_line, scope_summary=body.scope_summary,
        deliverables=body.deliverables, assumptions=body.assumptions,
        exclusions=body.exclusions, amount_minor=body.amount_minor,
        currency=body.currency, validity_days=body.validity_days, created_by=p.user.id,
    )
    db.add(item)
    db.flush()
    _event(db, org_id, p.user.id, "commercial.proposal_drafted", "proposal", item.id,
           body.workspace_id, {"opportunity_id": item.opportunity_id, "amount_minor": item.amount_minor, "currency": item.currency})
    db.commit()
    db.refresh(item)
    return item


@router.post("/proposals/{proposal_id}/submit-for-approval", response_model=ProposalOut)
def submit_proposal_for_approval(
    org_id: str, proposal_id: str,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    item = db.query(Proposal).filter_by(id=proposal_id, org_id=org_id).with_for_update().first()
    if item is None:
        raise HTTPException(404, "Proposal not found")
    _write(org_id, item.workspace_id, p, db)
    if item.status == "pending_approval":
        return item
    if item.status != "draft":
        raise HTTPException(409, "Only draft proposals can be submitted for approval")
    approval = Approval(
        org_id=org_id, workspace_id=item.workspace_id, action_type="pricing.change",
        resource_id=item.id, idempotency_key=f"proposal-pricing:{item.id}",
        request_payload={"proposal_title": item.title, "service_line": item.service_line,
                         "amount_minor": item.amount_minor, "currency": item.currency},
        requested_by=p.user.id,
    )
    db.add(approval)
    db.flush()
    item.status = "pending_approval"
    item.approval_id = approval.id
    _event(db, org_id, p.user.id, "commercial.proposal_submitted", "proposal", item.id,
           item.workspace_id, {"approval_id": approval.id, "action_type": "pricing.change"})
    _outbox(db, org_id, item.workspace_id, "commercial.proposal_submitted", "proposal", item.id,
            {"approval_id": approval.id})
    db.commit()
    db.refresh(item)
    return item


@router.post("/proposals/{proposal_id}/approve", response_model=ProposalOut)
def approve_proposal(
    org_id: str, proposal_id: str, body: ProposalDecision,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    item = db.query(Proposal).filter_by(id=proposal_id, org_id=org_id).with_for_update().first()
    if item is None:
        raise HTTPException(404, "Proposal not found")
    _write(org_id, item.workspace_id, p, db)
    if item.status != "pending_approval" or item.approval_id != body.approval_id:
        raise HTTPException(409, "Proposal is not awaiting this approval")
    require_approved_action(
        db, approval_id=body.approval_id, org_id=org_id,
        workspace_id=item.workspace_id, action_type="pricing.change",
        resource_id=item.id, actor_user_id=p.user.id,
    )
    item.status = "approved"
    item.approved_by = p.user.id
    item.approved_at = datetime.now(timezone.utc)
    _event(db, org_id, p.user.id, "commercial.proposal_approved", "proposal", item.id,
           item.workspace_id, {"approval_id": body.approval_id})
    _outbox(db, org_id, item.workspace_id, "commercial.proposal_approved", "proposal", item.id,
            {"approval_id": body.approval_id})
    db.commit()
    db.refresh(item)
    return item


@router.post("/proposals/{proposal_id}/reject", response_model=ProposalOut)
def reject_proposal(
    org_id: str, proposal_id: str, body: ProposalDecision,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    item = db.query(Proposal).filter_by(id=proposal_id, org_id=org_id).with_for_update().first()
    if item is None:
        raise HTTPException(404, "Proposal not found")
    require_founder_authority(db, org_id, p.user.id)
    if item.status != "pending_approval" or item.approval_id != body.approval_id:
        raise HTTPException(409, "Proposal is not awaiting this approval")
    approval = db.query(Approval).filter_by(
        id=body.approval_id, org_id=org_id, workspace_id=item.workspace_id,
        action_type="pricing.change", resource_id=item.id,
    ).with_for_update().first()
    if approval is None:
        raise HTTPException(404, "Proposal approval not found")
    if approval.status == ApprovalStatus.pending:
        approval.status = ApprovalStatus.rejected
        approval.decided_by = p.user.id
        approval.decision_note = body.note
        approval.decided_at = datetime.now(timezone.utc)
    elif approval.status != ApprovalStatus.rejected or not approval.decided_by or not has_founder_authority(db, org_id, approval.decided_by):
        raise HTTPException(409, "Proposal approval is no longer rejectable")
    item.status = "rejected"
    _event(db, org_id, p.user.id, "commercial.proposal_rejected", "proposal", item.id,
           item.workspace_id, {"approval_id": approval.id})
    _outbox(db, org_id, item.workspace_id, "commercial.proposal_rejected", "proposal", item.id,
            {"approval_id": approval.id})
    db.commit()
    db.refresh(item)
    return item


@router.get("/scope-changes", response_model=list[ScopeChangeOut])
def list_scope_changes(
    org_id: str, workspace_id: str = Query(min_length=1), project_id: str | None = None,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    role = require_membership(org_id, p, db)
    require_role(role, {Role.owner, Role.admin, Role.operator, Role.reviewer})
    _workspace(db, org_id, workspace_id)
    q = db.query(ScopeChangeRequest).filter_by(org_id=org_id, workspace_id=workspace_id)
    if project_id:
        _project(db, org_id, workspace_id, project_id)
        q = q.filter_by(project_id=project_id)
    return q.order_by(ScopeChangeRequest.created_at.desc()).limit(250).all()


@router.post("/scope-changes", response_model=ScopeChangeOut, status_code=201)
def create_scope_change(
    org_id: str, body: ScopeChangeCreate,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    _write(org_id, body.workspace_id, p, db)
    project = _project(db, org_id, body.workspace_id, body.project_id)
    item = ScopeChangeRequest(
        org_id=org_id, workspace_id=body.workspace_id, project_id=project.id,
        title=body.title, description=body.description, impact_summary=body.impact_summary,
        estimated_hours_delta=body.estimated_hours_delta,
        budget_delta_minor=body.budget_delta_minor,
        contract_value_delta_minor=body.contract_value_delta_minor,
        schedule_days_delta=body.schedule_days_delta, requested_by=p.user.id,
    )
    db.add(item)
    db.flush()
    _event(db, org_id, p.user.id, "scope_change.requested", "scope_change", item.id, body.workspace_id)
    _outbox(db, org_id, body.workspace_id, "operations.scope_change_requested", "scope_change", item.id, {"project_id": project.id})
    db.commit()
    db.refresh(item)
    return item


@router.post("/scope-changes/{change_id}/approve", response_model=ScopeChangeOut)
def approve_scope_change(
    org_id: str, change_id: str, body: ScopeChangeApproval,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    item = db.query(ScopeChangeRequest).filter_by(id=change_id, org_id=org_id).with_for_update().first()
    if item is None:
        raise HTTPException(404, "Scope change not found")
    require_membership(org_id, p, db)
    if item.status != "pending_approval":
        raise HTTPException(409, "Scope change is no longer pending")
    project = _project(db, org_id, item.workspace_id, item.project_id)
    require_approved_action(
        db, approval_id=body.approval_id, org_id=org_id,
        workspace_id=item.workspace_id, action_type="scope.change.accept",
        resource_id=item.id, actor_user_id=p.user.id,
    )
    new_budget = project.budget_minor + item.budget_delta_minor
    new_contract = project.contract_value_minor + item.contract_value_delta_minor
    new_hours = project.estimated_hours + item.estimated_hours_delta
    if min(new_budget, new_contract, new_hours) < 0:
        raise HTTPException(409, "Scope change would make project commercial values negative")
    project.budget_minor = new_budget
    project.contract_value_minor = new_contract
    project.estimated_hours = new_hours
    if project.due_date and item.schedule_days_delta:
        project.due_date = project.due_date + timedelta(days=item.schedule_days_delta)
    item.status = "approved"
    item.decided_by = p.user.id
    item.approval_id = body.approval_id
    item.decided_at = datetime.now(timezone.utc)
    _event(db, org_id, p.user.id, "scope_change.approved", "scope_change", item.id, item.workspace_id, {"approval_id": body.approval_id})
    _outbox(db, org_id, item.workspace_id, "operations.scope_change_approved", "scope_change", item.id, {"project_id": project.id, "approval_id": body.approval_id})
    db.commit()
    db.refresh(item)
    return item


@router.post("/scope-changes/{change_id}/reject", response_model=ScopeChangeOut)
def reject_scope_change(
    org_id: str, change_id: str, body: ScopeChangeReject,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    item = db.query(ScopeChangeRequest).filter_by(id=change_id, org_id=org_id).with_for_update().first()
    if item is None:
        raise HTTPException(404, "Scope change not found")
    require_founder_authority(db, org_id, p.user.id)
    if item.status != "pending_approval":
        raise HTTPException(409, "Scope change is no longer pending")
    item.status = "rejected"
    item.decided_by = p.user.id
    item.decided_at = datetime.now(timezone.utc)
    _event(db, org_id, p.user.id, "scope_change.rejected", "scope_change", item.id, item.workspace_id, {"note": body.note})
    db.commit()
    db.refresh(item)
    return item


@router.get("/time-entries", response_model=list[TimeEntryOut])
def list_time_entries(
    org_id: str, workspace_id: str = Query(min_length=1), project_id: str | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    role = require_membership(org_id, p, db)
    require_role(role, {Role.owner, Role.admin, Role.operator, Role.reviewer})
    _workspace(db, org_id, workspace_id)
    q = db.query(TimeEntry).filter_by(org_id=org_id, workspace_id=workspace_id)
    if project_id:
        _project(db, org_id, workspace_id, project_id)
        q = q.filter_by(project_id=project_id)
    return q.order_by(TimeEntry.started_at.desc()).limit(limit).all()


@router.post("/time-entries", response_model=TimeEntryOut, status_code=201)
def create_time_entry(
    org_id: str, body: TimeEntryCreate,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    _write(org_id, body.workspace_id, p, db)
    _project(db, org_id, body.workspace_id, body.project_id)
    if body.task_id:
        from app.models import Task
        if not db.query(Task.id).filter_by(id=body.task_id, org_id=org_id, workspace_id=body.workspace_id).first():
            raise HTTPException(404, "Task not found")
    item = TimeEntry(
        org_id=org_id, workspace_id=body.workspace_id, project_id=body.project_id,
        task_id=body.task_id, user_id=p.user.id, description=body.description,
        duration_minutes=body.duration_minutes, billable=body.billable,
        hourly_cost_minor=body.hourly_cost_minor, started_at=body.started_at,
    )
    db.add(item)
    db.flush()
    _event(db, org_id, p.user.id, "time_entry.recorded", "time_entry", item.id, body.workspace_id, {"project_id": body.project_id, "duration_minutes": body.duration_minutes})
    _outbox(db, org_id, body.workspace_id, "operations.time_entry_recorded", "time_entry", item.id, {"project_id": body.project_id, "duration_minutes": body.duration_minutes})
    db.commit()
    db.refresh(item)
    return item


@router.get("/project-costs", response_model=list[ProjectCostOut])
def list_project_costs(
    org_id: str, workspace_id: str = Query(min_length=1), project_id: str | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    role = require_membership(org_id, p, db)
    require_role(role, {Role.owner, Role.admin, Role.operator, Role.reviewer})
    _workspace(db, org_id, workspace_id)
    q = db.query(ProjectCost).filter_by(org_id=org_id, workspace_id=workspace_id)
    if project_id:
        _project(db, org_id, workspace_id, project_id)
        q = q.filter_by(project_id=project_id)
    return q.order_by(ProjectCost.incurred_at.desc()).limit(limit).all()


@router.post("/project-costs", response_model=ProjectCostOut, status_code=201)
def create_project_cost(
    org_id: str, body: ProjectCostCreate,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    _write(org_id, body.workspace_id, p, db)
    project = _project(db, org_id, body.workspace_id, body.project_id)
    if body.currency != project.currency:
        raise HTTPException(422, "Cost currency must match the project currency; FX conversion is not implemented")
    item = ProjectCost(
        org_id=org_id, workspace_id=body.workspace_id, project_id=body.project_id,
        category=body.category, description=body.description, amount_minor=body.amount_minor,
        currency=body.currency, incurred_at=body.incurred_at, recorded_by=p.user.id,
    )
    db.add(item)
    db.flush()
    _event(db, org_id, p.user.id, "project_cost.recorded", "project_cost", item.id, body.workspace_id, {"project_id": body.project_id, "amount_minor": body.amount_minor, "currency": body.currency})
    _outbox(db, org_id, body.workspace_id, "operations.project_cost_recorded", "project_cost", item.id, {"project_id": body.project_id})
    db.commit()
    db.refresh(item)
    return item


@router.get("/projects/{project_id}/financial-summary")
def project_financial_summary(
    org_id: str, project_id: str,
    workspace_id: str = Query(min_length=1),
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    require_founder_authority(db, org_id, p.user.id)
    project = _project(db, org_id, workspace_id, project_id)
    time_rows = db.query(TimeEntry.duration_minutes, TimeEntry.hourly_cost_minor).filter_by(
        org_id=org_id, workspace_id=workspace_id, project_id=project_id
    ).all()
    total_minutes = sum(row.duration_minutes for row in time_rows)
    labor_cost = sum(
        int((Decimal(row.duration_minutes * row.hourly_cost_minor) / Decimal(60)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        for row in time_rows
    )
    other_cost = db.query(func.coalesce(func.sum(ProjectCost.amount_minor), 0)).filter_by(
        org_id=org_id, workspace_id=workspace_id, project_id=project_id
    ).scalar()
    total_cost = labor_cost + int(other_cost or 0)
    return {
        "project_id": project.id,
        "currency": project.currency,
        "contract_value_minor": project.contract_value_minor,
        "budget_minor": project.budget_minor,
        "estimated_hours": project.estimated_hours,
        "actual_minutes": total_minutes,
        "actual_hours": round(total_minutes / 60, 2),
        "labor_cost_minor": labor_cost,
        "other_cost_minor": int(other_cost or 0),
        "actual_cost_minor": total_cost,
        "gross_margin_minor": project.contract_value_minor - total_cost,
        "budget_remaining_minor": project.budget_minor - total_cost,
        "margin_is_provisional": True,
        "note": "Management estimate only; excludes unrecorded time/costs, tax, FX, receivables and accounting adjustments.",
    }


@router.get("/exceptions")
def founder_exception_inbox(
    org_id: str, workspace_id: str = Query(min_length=1),
    limit: int = Query(default=100, ge=1, le=300),
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    """Read-only founder inbox for actionable approvals and delivery failures."""
    require_founder_authority(db, org_id, p.user.id)
    _workspace(db, org_id, workspace_id)
    items = []

    approvals = db.query(Approval).filter_by(
        org_id=org_id, workspace_id=workspace_id, status=ApprovalStatus.pending
    ).order_by(Approval.created_at.desc()).limit(limit).all()
    for a in approvals:
        items.append({
            "kind": "approval",
            "id": a.id,
            "title": f"Approval required: {a.action_type}",
            "status": "pending",
            "resource_id": a.resource_id,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "action_type": a.action_type,
        })

    executions = db.query(Execution).filter(
        Execution.org_id == org_id,
        Execution.workspace_id == workspace_id,
        Execution.status.in_([ExecutionStatus.failed, ExecutionStatus.retry_wait]),
    ).order_by(Execution.updated_at.desc()).limit(limit).all()
    for e in executions:
        items.append({
            "kind": "execution",
            "id": e.id,
            "title": f"Execution {e.status.value}: {e.id}",
            "status": e.status.value,
            "resource_id": e.task_id,
            "created_at": e.updated_at.isoformat() if e.updated_at else None,
            "error_code": e.error_code,
            "error_message": e.error_message,
            "attempt_count": e.attempt_count,
            "max_attempts": e.max_attempts,
        })

    blocked_tasks = db.query(Task).filter_by(
        org_id=org_id, workspace_id=workspace_id, status="blocked"
    ).order_by(Task.created_at.desc()).limit(limit).all()
    for task in blocked_tasks:
        items.append({
            "kind": "blocked_task",
            "id": task.id,
            "title": task.title,
            "status": task.status,
            "resource_id": task.id,
            "created_at": task.created_at.isoformat() if task.created_at else None,
        })

    items.sort(key=lambda x: x["created_at"] or "", reverse=True)
    return {"items": items[:limit], "count": min(len(items), limit)}


@router.get("/agent-performance")
def agent_performance(
    org_id: str, workspace_id: str = Query(min_length=1),
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    """Execution reliability metrics; not a substitute for accepted-work QA."""
    require_founder_authority(db, org_id, p.user.id)
    _workspace(db, org_id, workspace_id)
    rows = db.query(Execution.agent_id, Execution.status, func.count(Execution.id), func.sum(Execution.attempt_count)).filter(
        Execution.org_id == org_id, Execution.workspace_id == workspace_id
    ).group_by(Execution.agent_id, Execution.status).all()
    agents = {
        a.id: {"agent_id": a.id, "name": a.name, "department": a.department,
               "executions": 0, "succeeded": 0, "failed": 0, "active": 0,
               "attempts": 0}
        for a in db.query(Agent).filter_by(org_id=org_id, workspace_id=workspace_id).all()
    }
    for agent_id, status, count, attempts in rows:
        item = agents.setdefault(agent_id, {
            "agent_id": agent_id, "name": "Unknown agent", "department": "Unknown",
            "executions": 0, "succeeded": 0, "failed": 0, "active": 0, "attempts": 0,
        })
        n = int(count or 0)
        item["executions"] += n
        item["attempts"] += int(attempts or 0)
        state = status.value if hasattr(status, "value") else str(status)
        if state == "succeeded":
            item["succeeded"] += n
        elif state == "failed":
            item["failed"] += n
        elif state in {"queued", "claimed", "running", "retry_wait"}:
            item["active"] += n
    return {"items": sorted(agents.values(), key=lambda x: x["name"].lower())}

@router.get("/outbox-health")
def outbox_health(
    org_id: str,
    db: Session = Depends(get_db),
    p: Principal = Depends(get_principal),
):
    """Founder-only, organization-scoped outbox operational summary."""
    require_founder_authority(db, org_id, p.user.id)

    now = datetime.now(timezone.utc)

    status_rows = (
        db.query(OutboxEvent.status, func.count(OutboxEvent.id))
        .filter(OutboxEvent.org_id == org_id)
        .group_by(OutboxEvent.status)
        .all()
    )
    counts = {status: count for status, count in status_rows}

    oldest_pending = (
        db.query(func.min(OutboxEvent.created_at))
        .filter(
            OutboxEvent.org_id == org_id,
            OutboxEvent.status == "pending",
        )
        .scalar()
    )

    retrying_count = (
        db.query(func.count(OutboxEvent.id))
        .filter(
            OutboxEvent.org_id == org_id,
            OutboxEvent.status == "pending",
            OutboxEvent.attempts > 0,
        )
        .scalar()
    )

    expired_lease_count = (
        db.query(func.count(OutboxEvent.id))
        .filter(
            OutboxEvent.org_id == org_id,
            OutboxEvent.status == "processing",
            OutboxEvent.lease_expires_at.is_not(None),
            OutboxEvent.lease_expires_at <= now,
        )
        .scalar()
    )

    oldest_age = None
    if oldest_pending is not None:
        if oldest_pending.tzinfo is None:
            oldest_pending = oldest_pending.replace(tzinfo=timezone.utc)
        oldest_age = max(
            0,
            int((now - oldest_pending).total_seconds()),
        )

    return {
        "organization_id": org_id,
        "observed_at": now.isoformat(),
        "pending_count": counts.get("pending", 0),
        "oldest_pending_age_seconds": oldest_age,
        "processing_count": counts.get("processing", 0),
        "retrying_count": retrying_count or 0,
        "expired_lease_count": expired_lease_count or 0,
        "dead_letter_count": counts.get("dead_letter", 0),
        "published_count": counts.get("published", 0),
    }