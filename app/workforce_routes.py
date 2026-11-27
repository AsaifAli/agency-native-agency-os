"""Founder-governed workforce chart and explicit delegation APIs."""
import hashlib
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import Principal, get_principal, require_founder_authority, require_membership, require_role, require_workspace_access_from_context
from app.config import settings
from app.db import get_db
from app.models import Role, Workspace, Task, Agent
from app.autonomy_policy import action_disposition, ActionDisposition
from app.integrations.runtime_registry import is_runtime_available
from app.policy import assert_managed_agents_eligible
from app.audit import record_event
from app.workforce_models import (WorkforceUnit, WorkforceMember, WorkforceCapability, WorkforcePosition, Delegation, OrchestrationPlan, OrchestrationPlanDelegation, OrchestrationPlanDraft)
from app.workforce_schemas import (
    WorkforceInit, WorkforceCapabilityCreate, WorkforceCapabilityOut,
    DelegationCreate, DelegationOut, OrchestrationPlanCreate,
    PlanDraftCreate, PlanDraftApprove, PlanDraftReject, PlanDraftOut,
)
from app.workforce_service import initialize_workforce

router = APIRouter(prefix="/v1/orgs/{org_id}/workforce", tags=["workforce"])
WRITERS = {Role.owner, Role.admin, Role.operator}

from app.workforce_blueprints import list_specialists, list_blueprints


@router.get("/specialists")
def get_specialist_catalog(
    org_id: str,
    workspace_id: str = Query(min_length=1),
    db: Session = Depends(get_db),
    p: Principal = Depends(get_principal),
):
    """Read-only OS registry of Claude-owned specialist identities.

    Detailed instructions and skills are maintained as Claude integration source
    material; this endpoint exposes only stable identity and governance metadata.
    """
    require_membership(org_id, p, db)
    _workspace(db, org_id, workspace_id)
    return list_specialists()


@router.get("/blueprints")
def get_team_blueprints(
    org_id: str,
    workspace_id: str = Query(min_length=1),
    db: Session = Depends(get_db),
    p: Principal = Depends(get_principal),
):
    """Read-only, versioned team blueprints; no execution or activation occurs."""
    require_membership(org_id, p, db)
    _workspace(db, org_id, workspace_id)
    return list_blueprints()


def _workspace(db: Session, org_id: str, workspace_id: str):
    return require_workspace_access_from_context(org_id, workspace_id, db)


def _member(db: Session, org_id: str, workspace_id: str, member_id: str):
    row = db.query(WorkforceMember).filter_by(id=member_id, org_id=org_id, workspace_id=workspace_id).first()
    if row is None:
        raise HTTPException(404, "Workforce member not found")
    return row



def _member_is_in_reporting_tree(
    db: Session,
    org_id: str,
    workspace_id: str,
    root_member_id: str,
    candidate_member_id: str,
) -> bool:
    """Return true only when candidate is root or reports beneath root."""
    if root_member_id == candidate_member_id:
        return True
    candidate = _member(db, org_id, workspace_id, candidate_member_id)
    manager_id = candidate.manager_member_id
    visited = {candidate.id}
    while manager_id:
        if manager_id == root_member_id:
            return True
        if manager_id in visited:
            return False
        visited.add(manager_id)
        manager = db.query(WorkforceMember).filter_by(
            id=manager_id, org_id=org_id, workspace_id=workspace_id,
        ).first()
        if manager is None:
            return False
        manager_id = manager.manager_member_id


@router.get("")
def list_workforce(org_id: str, workspace_id: str = Query(min_length=1),
                   db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    require_membership(org_id, p, db)
    _workspace(db, org_id, workspace_id)
    units = db.query(WorkforceUnit).filter_by(org_id=org_id, workspace_id=workspace_id).all()
    members = db.query(WorkforceMember).filter_by(org_id=org_id, workspace_id=workspace_id).all()
    capabilities = db.query(WorkforceCapability).filter_by(org_id=org_id, workspace_id=workspace_id).all()
    positions = db.query(WorkforcePosition).filter_by(org_id=org_id, workspace_id=workspace_id).order_by(WorkforcePosition.department_key, WorkforcePosition.title).all()
    return {
        "units": [{"id":x.id,"parent_unit_id":x.parent_unit_id,"name":x.name,"unit_type":x.unit_type,"department_key":x.department_key,"description":x.description} for x in units],
        "members": [{"id":x.id,"unit_id":x.unit_id,"manager_member_id":x.manager_member_id,"agent_id":x.agent_id,"member_type":x.member_type,"name":x.name,"title":x.title,"department_key":x.department_key,"responsibilities":x.responsibilities,"autonomy_level":x.autonomy_level,"status":x.status,"is_founder_reserved":x.is_founder_reserved,"created_at":x.created_at,"updated_at":x.updated_at} for x in members],
        "capabilities": [{"id":x.id,"member_id":x.member_id,"capability_key":x.capability_key,"scope":x.scope,"allowed_data_classes":x.allowed_data_classes,"allowed_actions":x.allowed_actions,"tool_allowlist":x.tool_allowlist,"budget_minor":x.budget_minor,"currency":x.currency,"enabled":x.enabled} for x in capabilities],
        "positions": [{"id":x.id,"unit_id":x.unit_id,"team_unit_id":x.team_unit_id,"assigned_member_id":x.assigned_member_id,"position_key":x.position_key,"title":x.title,"department_key":x.department_key,"group_key":x.group_key,"team_key":x.team_key,"reports_to_position_key":x.reports_to_position_key,"responsibilities":x.responsibilities,"autonomy_ceiling":x.autonomy_ceiling,"status":x.status} for x in positions],
    }


@router.post("/{member_id}/capabilities", response_model=WorkforceCapabilityOut, status_code=201)
def add_capability(org_id: str, member_id: str, body: WorkforceCapabilityCreate,
                   workspace_id: str = Query(min_length=1), db: Session = Depends(get_db),
                   p: Principal = Depends(get_principal)):
    require_membership(org_id, p, db)
    require_founder_authority(db, org_id, p.user.id)
    _workspace(db, org_id, workspace_id)
    _member(db, org_id, workspace_id, member_id)
    invalid = set(body.allowed_data_classes) - {"synthetic", "public", "commercial", "confidential", "regulated"}
    if invalid:
        raise HTTPException(422, "Unsupported data class")
    row = db.query(WorkforceCapability).filter_by(member_id=member_id, capability_key=body.capability_key).one_or_none()
    if row is None:
        row = WorkforceCapability(org_id=org_id, workspace_id=workspace_id, member_id=member_id,
                                  capability_key=body.capability_key, scope=body.scope,
                                  allowed_data_classes=body.allowed_data_classes,
                                  allowed_actions=body.allowed_actions, tool_allowlist=body.tool_allowlist,
                                  budget_minor=body.budget_minor, currency=body.currency, enabled=False)
        db.add(row)
    else:
        row.scope, row.allowed_data_classes = body.scope, body.allowed_data_classes
        row.allowed_actions, row.tool_allowlist = body.allowed_actions, body.tool_allowlist
        row.budget_minor, row.currency, row.enabled = body.budget_minor, body.currency, False
    record_event(db, org_id, p.user.id, "workforce.capability_configured", "workforce_member", member_id,
                 workspace_id, {"capability": body.capability_key, "enabled": False})
    db.commit()
    db.refresh(row)
    return row


@router.post("/{member_id}/capabilities/{capability_id}/enable", response_model=WorkforceCapabilityOut)
def enable_capability(org_id: str, member_id: str, capability_id: str,
                      workspace_id: str = Query(min_length=1), db: Session = Depends(get_db),
                      p: Principal = Depends(get_principal)):
    require_membership(org_id, p, db)
    require_founder_authority(db, org_id, p.user.id)
    _workspace(db, org_id, workspace_id)
    member = _member(db, org_id, workspace_id, member_id)
    if member.is_founder_reserved:
        raise HTTPException(403, "Founder authority is not an agent capability")
    capability = db.query(WorkforceCapability).filter_by(
        id=capability_id, org_id=org_id, workspace_id=workspace_id, member_id=member.id
    ).with_for_update().first()
    if capability is None:
        raise HTTPException(404, "Workforce capability not found")
    if not capability.allowed_actions or any(
        action_disposition(action) != ActionDisposition.AUTONOMOUS
        for action in capability.allowed_actions
    ):
        raise HTTPException(403, "Capability contains an unknown or approval-required action")
    if capability.tool_allowlist:
        from app.tool_registry import get_tool
        for tool_key in capability.tool_allowlist:
            spec = get_tool(tool_key)
            if spec is None or spec.requires_approval:
                raise HTTPException(403, "Capability contains an unknown or approval-gated tool")
            if spec.required_action not in capability.allowed_actions:
                raise HTTPException(403, "Capability action does not authorize every selected tool")
            if not set(spec.allowed_data_classes).intersection(capability.allowed_data_classes):
                raise HTTPException(403, "Capability data class does not authorize every selected tool")
            scope_rank = {"self": 0, "team": 1, "workspace": 2}
            if capability.scope not in scope_rank or scope_rank[capability.scope] < scope_rank[spec.minimum_scope]:
                raise HTTPException(403, "Capability scope is narrower than the selected tool requires")
    if not capability.allowed_data_classes or set(capability.allowed_data_classes) - {"synthetic", "public"}:
        raise HTTPException(403, "Only synthetic and public data classes are currently eligible")
    agent = db.query(Agent).filter_by(
        id=member.agent_id, org_id=org_id, workspace_id=workspace_id
    ).first() if member.agent_id else None
    if agent is None:
        raise HTTPException(409, "Workforce member has no linked Agent definition")
    if agent.data_class.value not in capability.allowed_data_classes:
        raise HTTPException(403, "Capability does not cover the Agent data class")
    if not is_runtime_available(agent.runtime):
        raise HTTPException(409, "Agent runtime is not configured for this environment")
    if agent.runtime == "mock" and agent.data_class.value != "synthetic":
        raise HTTPException(403, "Mock runtime is restricted to synthetic data")
    if agent.runtime == "claude_managed_agents":
        try:
            assert_managed_agents_eligible(agent.data_class, client_authorized=False)
        except HTTPException as exc:
            raise HTTPException(403, "Managed Agents is not eligible for this data class") from exc
    capability.enabled = True
    record_event(db, org_id, p.user.id, "workforce.capability_enabled", "workforce_capability",
                 capability.id, workspace_id, {"member_id": member.id, "actions": capability.allowed_actions})
    db.commit()
    db.refresh(capability)
    return capability


@router.post("/{member_id}/activate")
def activate_member(org_id: str, member_id: str,
                    workspace_id: str = Query(min_length=1), db: Session = Depends(get_db),
                    p: Principal = Depends(get_principal)):
    require_membership(org_id, p, db)
    require_founder_authority(db, org_id, p.user.id)
    _workspace(db, org_id, workspace_id)
    member = db.query(WorkforceMember).filter_by(
        id=member_id, org_id=org_id, workspace_id=workspace_id
    ).with_for_update().first()
    if member is None:
        raise HTTPException(404, "Workforce member not found")
    if member.is_founder_reserved:
        raise HTTPException(403, "Founder authority cannot be activated as an agent")
    if member.status == "retired":
        raise HTTPException(409, "Retired workforce members cannot be reactivated")
    if not member.agent_id:
        raise HTTPException(409, "Workforce member has no linked Agent definition")
    agent = db.query(Agent).filter_by(
        id=member.agent_id, org_id=org_id, workspace_id=workspace_id
    ).with_for_update().first()
    if agent is None:
        raise HTTPException(409, "Linked Agent definition is missing")
    if not is_runtime_available(agent.runtime):
        raise HTTPException(409, "Agent runtime is not configured for this environment")
    grants = db.query(WorkforceCapability).filter_by(
        org_id=org_id, workspace_id=workspace_id, member_id=member.id, enabled=True
    ).all()
    execution_actions = {"task.execute", "research.execute", "report.generate"}
    eligible = [
        grant for grant in grants
        if agent.data_class.value in (grant.allowed_data_classes or [])
        and bool(set(grant.allowed_actions or []) & execution_actions)
        and not (grant.tool_allowlist or [])
    ]
    if not eligible:
        raise HTTPException(409, "An enabled, data-eligible execution capability is required")
    if agent.runtime == "mock" and agent.data_class.value != "synthetic":
        raise HTTPException(403, "Mock runtime is restricted to synthetic data")
    if agent.runtime == "claude_managed_agents":
        try:
            assert_managed_agents_eligible(agent.data_class, client_authorized=False)
        except HTTPException as exc:
            raise HTTPException(403, "Managed Agents is not eligible for this data class") from exc
    member.status = "active"
    agent.enabled = True
    db.query(WorkforcePosition).filter_by(
        org_id=org_id, workspace_id=workspace_id, assigned_member_id=member.id
    ).update({"status": "active"})
    record_event(db, org_id, p.user.id, "workforce.member_activated", "workforce_member",
                 member.id, workspace_id, {"agent_id": agent.id, "runtime": agent.runtime})
    db.commit()
    return {"member_id": member.id, "agent_id": agent.id, "status": member.status, "enabled": agent.enabled}


@router.post("/{member_id}/pause")
def pause_member(org_id: str, member_id: str,
                 workspace_id: str = Query(min_length=1), db: Session = Depends(get_db),
                 p: Principal = Depends(get_principal)):
    require_membership(org_id, p, db)
    require_founder_authority(db, org_id, p.user.id)
    _workspace(db, org_id, workspace_id)
    member = db.query(WorkforceMember).filter_by(
        id=member_id, org_id=org_id, workspace_id=workspace_id
    ).with_for_update().first()
    if member is None:
        raise HTTPException(404, "Workforce member not found")
    if member.is_founder_reserved:
        raise HTTPException(403, "Founder authority cannot be paused as an agent")
    member.status = "paused"
    if member.agent_id:
        agent = db.query(Agent).filter_by(
            id=member.agent_id, org_id=org_id, workspace_id=workspace_id
        ).with_for_update().first()
        if agent:
            agent.enabled = False
    db.query(WorkforceCapability).filter_by(
        org_id=org_id, workspace_id=workspace_id, member_id=member.id
    ).update({"enabled": False})
    db.query(WorkforcePosition).filter_by(
        org_id=org_id, workspace_id=workspace_id, assigned_member_id=member.id
    ).update({"status": "paused"})
    record_event(db, org_id, p.user.id, "workforce.member_paused", "workforce_member",
                 member.id, workspace_id, {"agent_id": member.agent_id})
    db.commit()
    return {"member_id": member.id, "status": member.status, "agent_enabled": False}



def _task_is_terminal(task: Task | None) -> bool:
    return bool(task and task.status in {"succeeded", "completed", "done"})


def _task_ancestors(db: Session, org_id: str, workspace_id: str, task_id: str) -> set[str]:
    ancestors: set[str] = set()
    current_id = task_id
    while True:
        parent_link = db.query(Delegation).filter_by(
            child_task_id=current_id, org_id=org_id, workspace_id=workspace_id
        ).first()
        if parent_link is None or parent_link.parent_task_id in ancestors:
            break
        ancestors.add(parent_link.parent_task_id)
        current_id = parent_link.parent_task_id
    return ancestors


def _delegation_readiness(db: Session, row: Delegation) -> str:
    if row.status in {"failed", "cancelled"}:
        return row.status
    if row.last_error_code:
        return "blocked"
    child = db.query(Task).filter_by(
        id=row.child_task_id, org_id=row.org_id, workspace_id=row.workspace_id
    ).first()
    if row.last_error_code:
        return "blocked"
    if child is None or child.status in {"failed", "cancelled", "review_changes_requested"}:
        return "failed"
    if _task_is_terminal(child):
        return "awaiting_review" if row.review_required and row.review_status == "pending" else "succeeded"
    if row.dependency_task_id:
        dependency = db.query(Task).filter_by(
            id=row.dependency_task_id, org_id=row.org_id, workspace_id=row.workspace_id
        ).first()
        if dependency is None or dependency.status in {"failed", "cancelled"}:
            return "failed"
        if not _task_is_terminal(dependency):
            return "blocked"
    return "ready"


def _refresh_plan(db: Session, plan: OrchestrationPlan, *, persist: bool = False) -> dict:
    links = db.query(OrchestrationPlanDelegation).filter_by(
        plan_id=plan.id
    ).order_by(OrchestrationPlanDelegation.ordinal.asc()).all()
    rows = [
        db.query(Delegation).filter_by(
            id=link.delegation_id, org_id=plan.org_id,
            workspace_id=plan.workspace_id,
        ).one()
        for link in links
    ]
    counts = {key: 0 for key in (
        "ready", "blocked", "awaiting_review", "failed",
        "succeeded", "running", "queued", "cancelled",
    )}
    for row in rows:
        effective_status = row.status
        if row.status not in {"running", "queued", "cancelled"}:
            effective_status = _delegation_readiness(db, row)
        counts[effective_status] = counts.get(effective_status, 0) + 1
        if persist and row.status != effective_status:
            row.status = effective_status
    if counts["failed"]:
        plan_status = "failed"
    elif counts["awaiting_review"]:
        plan_status = "awaiting_review"
    elif counts["ready"] or counts["blocked"] or counts["queued"] or counts["running"]:
        plan_status = "in_progress"
    elif counts["cancelled"] == len(rows) and rows:
        plan_status = "cancelled"
    elif counts["succeeded"] == len(rows) and rows:
        plan_status = "succeeded"
    else:
        plan_status = "planned"
    if persist:
        plan.status = plan_status
        plan.updated_at = datetime.now(timezone.utc)
    return {
        "id": plan.id, "objective": plan.objective, "status": plan_status,
        "task_count": len(rows), "ready_count": counts["ready"],
        "blocked_count": counts["blocked"],
        "awaiting_review_count": counts["awaiting_review"],
        "failed_count": counts["failed"], "succeeded_count": counts["succeeded"],
        "created_at": plan.created_at, "updated_at": plan.updated_at,
    }

def _create_delegation(db: Session, org_id: str, body: DelegationCreate,
                       actor_user_id: str, forced_parent_id: str | None = None) -> Delegation:
    _workspace(db, org_id, body.workspace_id)
    parent_id = forced_parent_id or body.parent_task_id
    parent = db.query(Task).filter_by(
        id=parent_id, org_id=org_id, workspace_id=body.workspace_id
    ).with_for_update().first()
    if parent is None:
        raise HTTPException(404, "Parent task not found")
    delegator = _member(db, org_id, body.workspace_id, body.delegated_by_member_id)
    assignee = _member(db, org_id, body.workspace_id, body.assigned_to_member_id)
    if delegator.is_founder_reserved or assignee.is_founder_reserved:
        raise HTTPException(403, "Agent delegation cannot grant or assign work to Founder authority")
    if assignee.manager_member_id != delegator.id:
        raise HTTPException(403, "Delegator must be the assigned member's direct manager")
    if delegator.status != "active" or assignee.status != "active":
        raise HTTPException(409, "Only active workforce members can delegate work")
    if delegator.autonomy_level < 2:
        raise HTTPException(403, "Delegator autonomy level does not permit task assignment")
    if delegator.agent_id is not None:
        manager_agent = db.query(Agent).filter_by(
            id=delegator.agent_id, org_id=org_id,
            workspace_id=body.workspace_id,
        ).first()
        if manager_agent is None or not manager_agent.enabled:
            raise HTTPException(409, "Delegating supervisor Agent definition is not enabled")
    agent = None
    if assignee.agent_id is not None:
        agent = db.query(Agent).filter_by(
            id=assignee.agent_id, org_id=org_id,
            workspace_id=body.workspace_id,
        ).first()
        if agent is None or not agent.enabled:
            raise HTTPException(409, "Assigned agent definition is not enabled")
    grants = db.query(WorkforceCapability).filter_by(
        org_id=org_id, workspace_id=body.workspace_id,
        member_id=assignee.id, enabled=True,
    ).all()
    execution_actions = {"task.execute", "research.execute", "report.generate"}
    eligible_grants = [
        grant for grant in grants
        if grant.allowed_actions
        and bool(set(grant.allowed_actions) & execution_actions)
        and not (grant.tool_allowlist or [])
        and (
            agent is None
            or agent.data_class.value in (grant.allowed_data_classes or [])
        )
    ]
    if not eligible_grants:
        raise HTTPException(403, "Assignee has no enabled, data-eligible execution capability without ungoverned tools")
    dependency = None
    if body.dependency_task_id:
        dependency = db.query(Task).filter_by(
            id=body.dependency_task_id, org_id=org_id,
            workspace_id=body.workspace_id,
        ).first()
        if dependency is None:
            raise HTTPException(404, "Dependency task not found")
        if dependency.id == parent_id or dependency.id in _task_ancestors(db, org_id, body.workspace_id, parent_id):
            raise HTTPException(409, "A task cannot depend on itself or an ancestor")
    blocked = bool(dependency and not _task_is_terminal(dependency))
    child = Task(
        org_id=org_id, workspace_id=body.workspace_id,
        title=body.child_title, description=body.child_description,
        status="blocked" if blocked else "queued",
        created_by=actor_user_id,
    )
    db.add(child)
    db.flush()
    row = Delegation(
        org_id=org_id, workspace_id=body.workspace_id,
        parent_task_id=parent_id, child_task_id=child.id,
        delegated_by_member_id=delegator.id,
        assigned_to_member_id=assignee.id,
        dependency_task_id=dependency.id if dependency else None,
        review_required=body.review_required, review_status="pending",
        status="blocked" if blocked else "ready",
        sequence_no=body.sequence_no,
    )
    db.add(row)
    db.flush()
    record_event(db, org_id, actor_user_id, "workforce.task_delegated",
                 "delegation", row.id, body.workspace_id, {
                     "parent_task_id": parent_id, "child_task_id": child.id,
                     "delegated_by_member_id": delegator.id,
                     "assigned_to_member_id": assignee.id,
                     "dependency_task_id": dependency.id if dependency else None,
                     "status": row.status,
                 })
    return row


@router.post("/delegations", response_model=DelegationOut, status_code=201)
def create_delegation(org_id: str, body: DelegationCreate, db: Session = Depends(get_db),
                      p: Principal = Depends(get_principal)):
    role = require_membership(org_id, p, db)
    require_role(role, WRITERS)
    _workspace(db, org_id, body.workspace_id)
    if body.depends_on_ordinal is not None:
        raise HTTPException(422, "depends_on_ordinal is only valid inside an orchestration plan")
    row = _create_delegation(db, org_id, body, p.user.id)
    db.commit()
    db.refresh(row)
    return row


def _persist_orchestration_plan(
    db: Session,
    *,
    org_id: str,
    body: OrchestrationPlanCreate,
    actor_user_id: str,
) -> tuple[dict, OrchestrationPlan, Task]:
    """Persist the approved plan graph inside the caller's transaction."""
    _workspace(db, org_id, body.workspace_id)
    creator = _member(db, org_id, body.workspace_id, body.created_by_member_id)
    if creator.is_founder_reserved or creator.status != "active":
        raise HTTPException(403, "Plan creator must be an active non-founder workforce member")
    if creator.department_key != "office_chief_of_staff" and creator.member_type != "supervisor":
        raise HTTPException(403, "Only the Chief of Staff or an active supervisor may create a plan")
    if creator.autonomy_level < 2:
        raise HTTPException(403, "Plan creator does not have planning authority")
    if creator.agent_id:
        agent = db.query(Agent).filter_by(
            id=creator.agent_id, org_id=org_id,
            workspace_id=body.workspace_id,
        ).first()
        if agent is None or not agent.enabled:
            raise HTTPException(409, "Supervisor agent definition is not enabled")

    for ordinal, spec in enumerate(body.tasks, start=1):
        if spec.depends_on_ordinal is not None:
            if spec.dependency_task_id is not None:
                raise HTTPException(422, "Use either dependency_task_id or depends_on_ordinal, not both")
            if spec.depends_on_ordinal >= ordinal:
                raise HTTPException(422, "Plan dependencies must reference an earlier task ordinal")

    root = Task(
        org_id=org_id, workspace_id=body.workspace_id,
        title=body.plan_title, description=body.objective,
        status="in_progress", created_by=actor_user_id,
    )
    db.add(root)
    db.flush()
    plan = OrchestrationPlan(
        org_id=org_id, workspace_id=body.workspace_id,
        root_task_id=root.id, created_by_member_id=creator.id,
        objective=body.objective, plan_title=body.plan_title,
        status="planned",
    )
    db.add(plan)
    db.flush()

    ordinal_to_task_id: dict[int, str] = {}
    for ordinal, task_body in enumerate(body.tasks, start=1):
        if task_body.workspace_id != body.workspace_id:
            raise HTTPException(422, "All plan tasks must use the plan workspace")
        if not _member_is_in_reporting_tree(
            db, org_id, body.workspace_id, creator.id,
            task_body.delegated_by_member_id,
        ):
            raise HTTPException(403, "Delegating supervisor is outside the plan creator's reporting tree")
        dependency_id = task_body.dependency_task_id
        if task_body.depends_on_ordinal is not None:
            dependency_id = ordinal_to_task_id.get(task_body.depends_on_ordinal)
            if dependency_id is None:
                raise HTTPException(422, "Plan dependency ordinal was not created")
        payload = task_body.model_dump(exclude={"depends_on_ordinal"})
        payload.update({
            "parent_task_id": root.id,
            "sequence_no": ordinal,
            "dependency_task_id": dependency_id,
        })
        bound = DelegationCreate.model_validate(payload)
        row = _create_delegation(
            db, org_id, bound, actor_user_id, forced_parent_id=root.id
        )
        ordinal_to_task_id[ordinal] = row.child_task_id
        db.add(OrchestrationPlanDelegation(
            plan_id=plan.id, delegation_id=row.id, ordinal=ordinal,
        ))
    # Session factories intentionally disable autoflush; persist the complete
    # plan-to-delegation graph before computing its summary.
    db.flush()
    summary = _refresh_plan(db, plan, persist=True)
    record_event(db, org_id, actor_user_id,
                 "workforce.orchestration_plan_created",
                 "orchestration_plan", plan.id, body.workspace_id, {
                     "root_task_id": root.id,
                     "task_count": len(body.tasks),
                     "created_by_member_id": creator.id,
                 })
    return summary, plan, root


@router.post("/plans", status_code=201)
def create_orchestration_plan(org_id: str, body: OrchestrationPlanCreate,
                              db: Session = Depends(get_db),
                              p: Principal = Depends(get_principal)):
    """Persist a founder-authorized, structured work plan."""
    require_membership(org_id, p, db)
    require_founder_authority(db, org_id, p.user.id)
    _workspace(db, org_id, body.workspace_id)
    try:
        summary, plan, root = _persist_orchestration_plan(
            db, org_id=org_id, body=body, actor_user_id=p.user.id
        )
        db.commit()
        return {**summary, "root_task_id": root.id}
    except Exception:
        db.rollback()
        raise


def _plan_draft_out(row: OrchestrationPlanDraft) -> dict:
    return {
        "id": row.id,
        "workspace_id": row.workspace_id,
        "execution_id": row.execution_id,
        "objective": row.objective,
        "plan_title": row.plan_title,
        "status": row.status,
        "suggested_plan": row.suggested_plan or {},
        "error_code": row.error_code,
        "approved_plan_id": row.approved_plan_id,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _validate_plan_draft_objective(value: str) -> None:
    # This is a lightweight submission guard, not a complete PII/DLP gateway.
    patterns = (
        r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        r"(?<!\w)(?:\+?\d[\s().-]?){9,15}(?!\w)",
        r"(?i)\b(?:sk-[A-Za-z0-9_-]{16,}|api[_ -]?key\s*[:=])",
    )
    if any(re.search(pattern, value) for pattern in patterns):
        raise HTTPException(422, "Remove personal contact details and credentials from the planning objective")


@router.post("/plan-drafts", status_code=202, response_model=PlanDraftOut)
def create_plan_draft(org_id: str, body: PlanDraftCreate,
                      db: Session = Depends(get_db),
                      p: Principal = Depends(get_principal)):
    """Queue a tool-free Claude planning request; never call the provider in this API transaction."""
    require_membership(org_id, p, db)
    require_founder_authority(db, org_id, p.user.id)
    _workspace(db, org_id, body.workspace_id)
    _validate_plan_draft_objective(body.objective)

    existing = db.query(OrchestrationPlanDraft).filter_by(
        org_id=org_id, workspace_id=body.workspace_id,
        idempotency_key=body.idempotency_key,
    ).with_for_update().one_or_none()
    if existing is not None:
        if existing.objective != body.objective or existing.plan_title != body.plan_title:
            raise HTTPException(409, "Plan draft idempotency key was used for a different objective")
        return _plan_draft_out(existing)

    chief = db.query(WorkforceMember).filter_by(
        org_id=org_id, workspace_id=body.workspace_id,
        department_key="office_chief_of_staff",
    ).one_or_none()
    if chief is None or chief.status != "active" or chief.is_founder_reserved or chief.autonomy_level < 2:
        raise HTTPException(409, "Chief of Staff must be active before generating a plan proposal")
    agent = db.query(Agent).filter_by(
        id=chief.agent_id, org_id=org_id, workspace_id=body.workspace_id,
    ).first() if chief.agent_id else None
    if agent is None or not agent.enabled or agent.runtime != "claude_managed_agents":
        raise HTTPException(409, "Chief of Staff must have an enabled Claude Managed Agents definition")
    if agent.data_class.value not in {"synthetic", "public"}:
        raise HTTPException(403, "Plan drafting is limited to synthetic or public data")
    if not settings.claude_managed_agents_enabled or not is_runtime_available("claude_managed_agents"):
        raise HTTPException(503, "Claude Managed Agents is not configured for this environment")
    grant = db.query(WorkforceCapability).filter_by(
        org_id=org_id, workspace_id=body.workspace_id,
        member_id=chief.id, enabled=True,
    ).all()
    if not any(
        "plan.generate" in (item.allowed_actions or [])
        and agent.data_class.value in (item.allowed_data_classes or [])
        and not (item.tool_allowlist or [])
        for item in grant
    ):
        raise HTTPException(403, "Chief of Staff requires an enabled plan.generate capability for this data class")

    from app.execution_service import create_execution, ExecutionServiceError
    task = Task(
        org_id=org_id, workspace_id=body.workspace_id,
        title=f"Draft plan: {body.plan_title}",
        description=body.objective, status="queued", created_by=p.user.id,
    )
    db.add(task)
    db.flush()
    idempotency_digest = hashlib.sha256(
        f"{org_id}:{body.workspace_id}:{body.idempotency_key}".encode()
    ).hexdigest()
    try:
        execution = create_execution(
            db, org_id=org_id, workspace_id=body.workspace_id,
            task_id=task.id, agent_id=agent.id, requested_by=p.user.id,
            idempotency_key=f"plan-draft:{idempotency_digest}",
            required_capability_action="plan.generate",
        )
    except ExecutionServiceError as exc:
        db.rollback()
        raise HTTPException(409, "Chief of Staff planning execution is not eligible") from exc

    row = OrchestrationPlanDraft(
        org_id=org_id, workspace_id=body.workspace_id,
        task_id=task.id, execution_id=execution.id,
        requested_by_user_id=p.user.id, created_by_member_id=chief.id,
        idempotency_key=body.idempotency_key,
        objective=body.objective, plan_title=body.plan_title,
        status="queued", suggested_plan={},
    )
    db.add(row)
    db.flush()
    execution.request_metadata = {
        "purpose": "workforce.plan_draft",
        "plan_draft_id": row.id,
        "schema_version": 1,
    }
    record_event(db, org_id, p.user.id, "workforce.plan_draft_queued",
                 "orchestration_plan_draft", row.id, body.workspace_id,
                 {"execution_id": execution.id, "chief_of_staff_member_id": chief.id})
    db.commit()
    db.refresh(row)
    return _plan_draft_out(row)


@router.get("/plan-drafts")
def list_plan_drafts(org_id: str, workspace_id: str = Query(min_length=1),
                     db: Session = Depends(get_db),
                     p: Principal = Depends(get_principal)):
    require_membership(org_id, p, db)
    require_founder_authority(db, org_id, p.user.id)
    _workspace(db, org_id, workspace_id)
    rows = db.query(OrchestrationPlanDraft).filter_by(
        org_id=org_id, workspace_id=workspace_id,
    ).order_by(OrchestrationPlanDraft.created_at.desc()).limit(100).all()
    return [_plan_draft_out(row) for row in rows]


@router.get("/plan-drafts/{draft_id}", response_model=PlanDraftOut)
def get_plan_draft(org_id: str, draft_id: str,
                   workspace_id: str = Query(min_length=1),
                   db: Session = Depends(get_db),
                   p: Principal = Depends(get_principal)):
    require_membership(org_id, p, db)
    require_founder_authority(db, org_id, p.user.id)
    _workspace(db, org_id, workspace_id)
    row = db.query(OrchestrationPlanDraft).filter_by(
        id=draft_id, org_id=org_id, workspace_id=workspace_id,
    ).first()
    if row is None:
        raise HTTPException(404, "Plan draft not found")
    return _plan_draft_out(row)


@router.post("/plan-drafts/{draft_id}/reject")
def reject_plan_draft(org_id: str, draft_id: str, body: PlanDraftReject,
                      workspace_id: str = Query(min_length=1),
                      db: Session = Depends(get_db),
                      p: Principal = Depends(get_principal)):
    require_membership(org_id, p, db)
    require_founder_authority(db, org_id, p.user.id)
    _workspace(db, org_id, workspace_id)
    row = db.query(OrchestrationPlanDraft).filter_by(
        id=draft_id, org_id=org_id, workspace_id=workspace_id,
    ).with_for_update().first()
    if row is None:
        raise HTTPException(404, "Plan draft not found")
    if row.status != "ready_for_review":
        raise HTTPException(409, "Only a validated proposal can be rejected")
    row.status = "rejected"
    row.reviewed_by_user_id = p.user.id
    row.reviewed_at = datetime.now(timezone.utc)
    row.updated_at = datetime.now(timezone.utc)
    task = db.query(Task).filter_by(
        id=row.task_id, org_id=org_id, workspace_id=workspace_id,
    ).with_for_update().first()
    if task:
        task.status = "cancelled"
    record_event(db, org_id, p.user.id, "workforce.plan_draft_rejected",
                 "orchestration_plan_draft", row.id, workspace_id,
                 {"reason": body.reason, "execution_id": row.execution_id})
    db.commit()
    return _plan_draft_out(row)


@router.post("/plan-drafts/{draft_id}/approve")
def approve_plan_draft(org_id: str, draft_id: str, body: PlanDraftApprove,
                       workspace_id: str = Query(min_length=1),
                       db: Session = Depends(get_db),
                       p: Principal = Depends(get_principal)):
    require_membership(org_id, p, db)
    require_founder_authority(db, org_id, p.user.id)
    _workspace(db, org_id, workspace_id)
    row = db.query(OrchestrationPlanDraft).filter_by(
        id=draft_id, org_id=org_id, workspace_id=workspace_id,
    ).with_for_update().first()
    if row is None:
        raise HTTPException(404, "Plan draft not found")
    if row.status != "ready_for_review" or not row.suggested_plan:
        raise HTTPException(409, "Only a validated proposal can be approved")

    suggested = row.suggested_plan
    expected_ordinals = set(range(1, len(suggested.get("tasks", [])) + 1))
    supplied_ordinals = {item.ordinal for item in body.assignments}
    if supplied_ordinals != expected_ordinals:
        raise HTTPException(422, "Every proposed task requires exactly one founder-approved assignment")

    assignments = {item.ordinal: item for item in body.assignments}
    task_specs: list[DelegationCreate] = []
    for ordinal, task_spec in enumerate(suggested["tasks"], start=1):
        assignment = assignments[ordinal]
        assignee = _member(db, org_id, workspace_id, assignment.assigned_to_member_id)
        if assignee.department_key not in {
            task_spec["department_key"], f"{task_spec['department_key']}_head",
        }:
            raise HTTPException(403, "Assignee does not belong to the proposed department")
        if not assignment.review_required:
            raise HTTPException(403, "Chief of Staff proposals require founder review on every task")
        description = task_spec["description"]
        criteria = task_spec.get("acceptance_criteria") or []
        if criteria:
            description += "\n\nAcceptance criteria:\n" + "\n".join(
                f"- {item}" for item in criteria
            )
        task_specs.append(DelegationCreate(
            workspace_id=workspace_id,
            parent_task_id="server-owned-root",
            child_title=task_spec["title"],
            child_description=description,
            delegated_by_member_id=assignment.delegated_by_member_id,
            assigned_to_member_id=assignment.assigned_to_member_id,
            depends_on_ordinal=task_spec.get("depends_on_ordinal"),
            review_required=True,
            sequence_no=ordinal,
        ))

    plan_body = OrchestrationPlanCreate(
        workspace_id=workspace_id,
        objective=row.objective,
        created_by_member_id=row.created_by_member_id,
        plan_title=row.plan_title,
        tasks=task_specs,
    )
    try:
        summary, plan, root = _persist_orchestration_plan(
            db, org_id=org_id, body=plan_body, actor_user_id=p.user.id
        )
    except Exception:
        db.rollback()
        raise

    row.status = "approved"
    row.approved_plan_id = plan.id
    row.reviewed_by_user_id = p.user.id
    row.reviewed_at = datetime.now(timezone.utc)
    row.updated_at = datetime.now(timezone.utc)
    draft_task = db.query(Task).filter_by(
        id=row.task_id, org_id=org_id, workspace_id=workspace_id,
    ).with_for_update().first()
    if draft_task:
        draft_task.status = "succeeded"
    record_event(db, org_id, p.user.id, "workforce.plan_draft_approved",
                 "orchestration_plan_draft", row.id, workspace_id,
                 {"approved_plan_id": plan.id, "root_task_id": root.id,
                  "task_count": len(task_specs)})
    db.commit()
    return {**summary, "root_task_id": root.id,
            "draft_id": row.id, "draft_status": row.status}


@router.get("/plans")
def list_orchestration_plans(org_id: str, workspace_id: str = Query(min_length=1),
                             db: Session = Depends(get_db),
                             p: Principal = Depends(get_principal)):
    require_membership(org_id, p, db)
    _workspace(db, org_id, workspace_id)
    plans = db.query(OrchestrationPlan).filter_by(
        org_id=org_id, workspace_id=workspace_id
    ).order_by(OrchestrationPlan.created_at.desc()).limit(100).all()
    result = [_refresh_plan(db, plan, persist=False) for plan in plans]
    return result


@router.get("/plans/{plan_id}")
def get_orchestration_plan(org_id: str, plan_id: str,
                           workspace_id: str = Query(min_length=1),
                           db: Session = Depends(get_db),
                           p: Principal = Depends(get_principal)):
    require_membership(org_id, p, db)
    _workspace(db, org_id, workspace_id)
    plan = db.query(OrchestrationPlan).filter_by(
        id=plan_id, org_id=org_id, workspace_id=workspace_id
    ).first()
    if plan is None:
        raise HTTPException(404, "Orchestration plan not found")
    summary = _refresh_plan(db, plan, persist=False)
    links = db.query(OrchestrationPlanDelegation).filter_by(
        plan_id=plan.id
    ).order_by(OrchestrationPlanDelegation.ordinal.asc()).all()
    items = []
    for link in links:
        row = db.query(Delegation).filter_by(
            id=link.delegation_id, org_id=org_id,
            workspace_id=workspace_id,
        ).one()
        child = db.query(Task).filter_by(
            id=row.child_task_id, org_id=org_id,
            workspace_id=workspace_id,
        ).first()
        effective_status = (
            row.status if row.status in {"running", "queued", "cancelled"}
            else _delegation_readiness(db, row)
        )
        items.append({
            "ordinal": link.ordinal, "delegation_id": row.id,
            "child_task_id": row.child_task_id,
            "title": child.title if child else None,
            "assignee_member_id": row.assigned_to_member_id,
            "dependency_task_id": row.dependency_task_id,
            "status": effective_status, "review_status": row.review_status,
            "review_required": row.review_required,
            "last_error_code": row.last_error_code,
        })
    db.commit()
    return {**summary, "root_task_id": plan.root_task_id, "tasks": items}


@router.post("/plans/{plan_id}/refresh")
def refresh_orchestration_plan(org_id: str, plan_id: str,
                               workspace_id: str = Query(min_length=1),
                               db: Session = Depends(get_db),
                               p: Principal = Depends(get_principal)):
    require_membership(org_id, p, db)
    require_founder_authority(db, org_id, p.user.id)
    _workspace(db, org_id, workspace_id)
    plan = db.query(OrchestrationPlan).filter_by(
        id=plan_id, org_id=org_id,
        workspace_id=workspace_id,
    ).with_for_update().first()
    if plan is None:
        raise HTTPException(404, "Orchestration plan not found")
    summary = _refresh_plan(db, plan, persist=True)
    if summary["status"] == "succeeded":
        root = db.query(Task).filter_by(
            id=plan.root_task_id, org_id=org_id,
            workspace_id=workspace_id,
        ).with_for_update().first()
        if root:
            root.status = "succeeded"
    record_event(db, org_id, p.user.id,
                 "workforce.orchestration_plan_refreshed",
                 "orchestration_plan", plan.id, workspace_id,
                 {"status": plan.status})
    db.commit()
    return summary


@router.get("/delegations", response_model=list[DelegationOut])
def list_delegations(org_id: str, workspace_id: str = Query(min_length=1),
                     db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    require_membership(org_id, p, db)
    _workspace(db, org_id, workspace_id)
    return db.query(Delegation).filter_by(org_id=org_id, workspace_id=workspace_id).order_by(Delegation.created_at.desc()).limit(500).all()


@router.post("/delegations/{delegation_id}/requeue")
def requeue_delegation(org_id: str, delegation_id: str,
                       workspace_id: str = Query(min_length=1),
                       db: Session = Depends(get_db),
                       p: Principal = Depends(get_principal)):
    require_membership(org_id, p, db)
    require_founder_authority(db, org_id, p.user.id)
    _workspace(db, org_id, workspace_id)
    row = db.query(Delegation).filter_by(
        id=delegation_id, org_id=org_id, workspace_id=workspace_id
    ).with_for_update().first()
    if row is None:
        raise HTTPException(404, "Delegation not found")
    if row.status != "blocked" or not row.last_error_code:
        raise HTTPException(409, "Only blocked delegations with a recorded queue error can be requeued")
    assignee = _member(db, org_id, workspace_id, row.assigned_to_member_id)
    if assignee.status != "active":
        raise HTTPException(409, "Assignee must be active before requeue")
    task = db.query(Task).filter_by(
        id=row.child_task_id, org_id=org_id, workspace_id=workspace_id
    ).with_for_update().first()
    if task is None:
        raise HTTPException(404, "Delegated task not found")
    task.status = "queued"
    row.status = "ready"
    prior_error = row.last_error_code
    row.last_error_code = None
    row.updated_at = datetime.now(timezone.utc)
    record_event(db, org_id, p.user.id, "workforce.delegation_requeued",
                 "delegation", row.id, workspace_id,
                 {"previous_error_code": prior_error})
    db.commit()
    return {"id": row.id, "status": row.status}


@router.post("/delegations/{delegation_id}/review")
def review_delegation(org_id: str, delegation_id: str, decision: str,
                      workspace_id: str = Query(min_length=1), db: Session = Depends(get_db),
                      p: Principal = Depends(get_principal)):
    require_membership(org_id, p, db)
    require_founder_authority(db, org_id, p.user.id)
    _workspace(db, org_id, workspace_id)
    row = db.query(Delegation).filter_by(
        id=delegation_id, org_id=org_id, workspace_id=workspace_id
    ).with_for_update().first()
    if row is None:
        raise HTTPException(404, "Delegation not found")
    if row.review_status != "pending":
        raise HTTPException(409, "Delegation review is not pending")
    if decision not in {"approved", "changes_requested", "waived"}:
        raise HTTPException(422, "Unsupported delegation decision")
    if decision == "waived" and row.review_required:
        raise HTTPException(403, "Required review cannot be waived")
    child = db.query(Task).filter_by(
        id=row.child_task_id, org_id=org_id, workspace_id=workspace_id
    ).with_for_update().first()
    if child is None:
        raise HTTPException(404, "Delegated child task not found")
    if decision in {"approved", "waived"} and not _task_is_terminal(child):
        raise HTTPException(409, "A child task must be completed before it can pass review")
    if decision in {"approved", "waived"}:
        row.review_status = decision
        row.status = "succeeded"
    else:
        row.review_status = decision
        row.status = "failed"
        child.status = "review_changes_requested"
        row.last_error_code = "FOUNDER_REVIEW_CHANGES_REQUESTED"
    link = db.query(OrchestrationPlanDelegation).filter_by(
        delegation_id=row.id
    ).first()
    if link:
        plan = db.query(OrchestrationPlan).filter_by(
            id=link.plan_id, org_id=org_id,
            workspace_id=workspace_id,
        ).with_for_update().first()
        if plan:
            summary = _refresh_plan(db, plan, persist=True)
            if summary["succeeded_count"] == summary["task_count"] and summary["task_count"]:
                root = db.query(Task).filter_by(
                    id=plan.root_task_id, org_id=org_id,
                    workspace_id=workspace_id,
                ).with_for_update().first()
                if root:
                    root.status = "succeeded"
    record_event(db, org_id, p.user.id, "workforce.delegation_reviewed",
                 "delegation", row.id, workspace_id, {
                     "decision": decision, "status": row.status,
                 })
    db.commit()
    return {"id": row.id, "review_status": row.review_status, "status": row.status}
