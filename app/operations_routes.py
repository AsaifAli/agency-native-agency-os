"""Workspace-scoped delivery operations and commercial controls.

These endpoints persist operational records. They do not send invoices, collect
payments, authorize scope changes without a founder approval, or dispatch events.
"""
from datetime import datetime, timedelta, timezone
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

from app.domain_models import Project, Opportunity
from app.operations_models import ServicePlaybook, Proposal, ScopeChangeRequest, TimeEntry, ProjectCost
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
    require_role(role, WRITERS)
    _workspace(db, org_id, workspace_id)


def _event(db, org_id, actor_id, event_type, resource_type, resource_id, workspace_id, payload=None):
    record_event(db, org_id, actor_id, event_type, resource_type, resource_id, workspace_id, payload or {})


def _outbox(db, org_id, workspace_id, event_type, aggregate_type, aggregate_id, payload):
    db.add(OutboxEvent(
        org_id=org_id, workspace_id=workspace_id, event_type=event_type,
        schema_version=1, aggregate_type=aggregate_type, aggregate_id=aggregate_id,
        idempotency_key=f"{event_type}:{aggregate_id}", payload=payload,
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


@router.get("/proposals", response_model=list[ProposalOut])
def list_proposals(
    org_id: str, workspace_id: str = Query(min_length=1), opportunity_id: str | None = None,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    role = require_membership(org_id, p, db)
    require_role(role, {Role.owner, Role.admin, Role.operator, Role.reviewer})
    _workspace(db, org_id, workspace_id)
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