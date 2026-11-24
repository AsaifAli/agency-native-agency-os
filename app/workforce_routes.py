"""Founder-governed workforce chart and explicit delegation APIs."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import Principal, get_principal, require_founder_authority, require_membership, require_role
from app.db import get_db
from app.models import Role, Workspace, Task, Agent
from app.audit import record_event
from app.workforce_models import WorkforceUnit, WorkforceMember, WorkforceCapability, Delegation
from app.workforce_schemas import (
    WorkforceInit, WorkforceMemberOut, WorkforceUnitOut,
    WorkforceCapabilityCreate, WorkforceCapabilityOut, DelegationCreate, DelegationOut,
)
from app.workforce_service import initialize_workforce

router = APIRouter(prefix="/v1/orgs/{org_id}/workforce", tags=["workforce"])
WRITERS = {Role.owner, Role.admin, Role.operator}


def _workspace(db: Session, org_id: str, workspace_id: str):
    row = db.query(Workspace).filter_by(id=workspace_id, org_id=org_id).first()
    if row is None:
        raise HTTPException(404, "Workspace not found")
    return row


def _member(db: Session, org_id: str, workspace_id: str, member_id: str):
    row = db.query(WorkforceMember).filter_by(
        id=member_id, org_id=org_id, workspace_id=workspace_id
    ).first()
    if row is None:
        raise HTTPException(404, "Workforce member not found")
    return row


@router.post("/initialize")
def initialize(org_id: str, body: WorkforceInit, db: Session = Depends(get_db),
               p: Principal = Depends(get_principal)):
    require_membership(org_id, p, db)
    require_founder_authority(db, org_id, p.user.id)
    _workspace(db, org_id, body.workspace_id)
    try:
        result = initialize_workforce(db, org_id=org_id, workspace_id=body.workspace_id)
        record_event(db, org_id, p.user.id, "workforce.initialized", "workforce", body.workspace_id,
                     body.workspace_id, result)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


@router.get("")
def list_workforce(org_id: str, workspace_id: str = Query(min_length=1),
                   db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    require_membership(org_id, p, db)
    _workspace(db, org_id, workspace_id)
    units = db.query(WorkforceUnit).filter_by(org_id=org_id, workspace_id=workspace_id).order_by(WorkforceUnit.unit_type, WorkforceUnit.name).all()
    members = db.query(WorkforceMember).filter_by(org_id=org_id, workspace_id=workspace_id).order_by(WorkforceMember.department_key, WorkforceMember.name).all()
    return {"units":[WorkforceUnitOut.model_validate(x).model_dump(mode="json") for x in units],
            "members":[WorkforceMemberOut.model_validate(x).model_dump(mode="json") for x in members]}


@router.post("/{member_id}/capabilities", response_model=WorkforceCapabilityOut, status_code=201)
def add_capability(org_id: str, member_id: str, body: WorkforceCapabilityCreate,
                   workspace_id: str = Query(min_length=1), db: Session = Depends(get_db),
                   p: Principal = Depends(get_principal)):
    require_membership(org_id, p, db)
    require_founder_authority(db, org_id, p.user.id)
    _workspace(db, org_id, workspace_id)
    _member(db, org_id, workspace_id, member_id)
    invalid_classes = set(body.allowed_data_classes) - {"synthetic", "public", "commercial", "confidential", "regulated"}
    if invalid_classes:
        raise HTTPException(422, "Unsupported data class")
    row = db.query(WorkforceCapability).filter_by(member_id=member_id, capability_key=body.capability_key).one_or_none()
    if row is None:
        row = WorkforceCapability(org_id=org_id, workspace_id=workspace_id, member_id=member_id,
                                  capability_key=body.capability_key, scope=body.scope,
                                  allowed_data_classes=body.allowed_data_classes, allowed_actions=body.allowed_actions,
                                  tool_allowlist=body.tool_allowlist, budget_minor=body.budget_minor, currency=body.currency,
                                  enabled=False)
        db.add(row)
    else:
        row.scope=body.scope
        row.allowed_data_classes=body.allowed_data_classes
        row.allowed_actions=body.allowed_actions
        row.tool_allowlist=body.tool_allowlist
        row.budget_minor=body.budget_minor
        row.currency=body.currency
        row.enabled=False
    record_event(db, org_id, p.user.id, "workforce.capability_configured", "workforce_member", member_id,
                 workspace_id, {"capability": body.capability_key, "enabled": False})
    db.commit()
    db.refresh(row)
    return row


@router.post("/delegations", response_model=DelegationOut, status_code=201)
def create_delegation(org_id: str, body: DelegationCreate, db: Session = Depends(get_db),
                      p: Principal = Depends(get_principal)):
    role = require_membership(org_id, p, db)
    require_role(role, WRITERS)
    _workspace(db, org_id, body.workspace_id)
    parent = db.query(Task).filter_by(id=body.parent_task_id, org_id=org_id, workspace_id=body.workspace_id).first()
    if parent is None:
        raise HTTPException(404, "Parent task not found")
    delegator = _member(db, org_id, body.workspace_id, body.delegated_by_member_id)
    assignee = _member(db, org_id, body.workspace_id, body.assigned_to_member_id)
    if delegator.status != "active" or assignee.status != "active":
        raise HTTPException(409, "Only active workforce members can delegate work")
    if delegator.is_founder_reserved:
        raise HTTPException(403, "Founder authority must not be represented as an autonomous agent member")
    if delegator.manager_member_id != assignee.id and delegator.id != assignee.manager_member_id:
        raise HTTPException(403, "Delegation must follow the configured reporting relationship")
    if assignee.is_founder_reserved:
        raise HTTPException(403, "Autonomous members cannot delegate tasks to the Founder")
    dependency = None
    if body.dependency_task_id:
        dependency = db.query(Task).filter_by(id=body.dependency_task_id, org_id=org_id, workspace_id=body.workspace_id).first()
        if dependency is None:
            raise HTTPException(404, "Dependency task not found")
    child = Task(org_id=org_id, workspace_id=body.workspace_id, title=body.child_title,
                 description=body.child_description, status="queued", created_by=p.user.id)
    db.add(child)
    db.flush()
    row = Delegation(org_id=org_id, workspace_id=body.workspace_id,
                     parent_task_id=parent.id, child_task_id=child.id,
                     delegated_by_member_id=delegator.id, assigned_to_member_id=assignee.id,
                     dependency_task_id=dependency.id if dependency else None,
                     review_required=body.review_required, review_status="pending")
    db.add(row)
    record_event(db, org_id, p.user.id, "workforce.task_delegated", "delegation", row.id,
                 body.workspace_id, {"parent_task_id": parent.id, "child_task_id": child.id,
                                     "delegated_by_member_id": delegator.id,
                                     "assigned_to_member_id": assignee.id})
    db.commit()
    db.refresh(row)
    return row


@router.get("/delegations", response_model=list[DelegationOut])
def list_delegations(org_id: str, workspace_id: str = Query(min_length=1),
                     db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    require_membership(org_id, p, db)
    _workspace(db, org_id, workspace_id)
    return db.query(Delegation).filter_by(org_id=org_id, workspace_id=workspace_id).order_by(Delegation.created_at.desc()).limit(500).all()


@router.post("/delegations/{delegation_id}/review")
def review_delegation(org_id: str, delegation_id: str, decision: str,
                      workspace_id: str = Query(min_length=1), db: Session = Depends(get_db),
                      p: Principal = Depends(get_principal)):
    require_membership(org_id, p, db)
    require_founder_authority(db, org_id, p.user.id)
    _workspace(db, org_id, workspace_id)
    row = db.query(Delegation).filter_by(id=delegation_id, org_id=org_id, workspace_id=workspace_id).with_for_update().first()
    if row is None:
        raise HTTPException(404, "Delegation not found")
    if row.review_status != "pending":
        raise HTTPException(409, "Delegation review is not pending")
    if decision not in {"approved", "changes_requested", "waived"}:
        raise HTTPException(422, "Unsupported delegation decision")
    if decision == "waived" and row.review_required:
        raise HTTPException(403, "Required review cannot be waived")
    row.review_status = decision
    record_event(db, org_id, p.user.id, "workforce.delegation_reviewed", "delegation", row.id,
                 workspace_id, {"decision": decision, "review_required": row.review_required})
    db.commit()
    return {"id": row.id, "review_status": row.review_status}
