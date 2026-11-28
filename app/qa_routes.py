"""Workspace-scoped QA issue lifecycle with audit-backed transitions."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth import (
    Principal,
    get_principal,
    has_founder_authority,
    require_membership,
    require_workspace_access_from_context,
)
from app.audit import record_event
from app.db import get_db
from app.domain_models import Milestone, Project, QAIssue
from app.models import EvaluationRun, Role, Task


router = APIRouter(prefix="/v1/orgs/{org_id}/qa", tags=["quality-assurance"])

QA_WRITERS = {Role.owner, Role.admin, Role.operator, Role.reviewer}
QA_READERS = {Role.owner, Role.admin, Role.operator, Role.reviewer, Role.viewer}
VALID_SEVERITIES = {"blocker", "critical", "major", "minor", "cosmetic"}
TRANSITIONS = {
    "open": {"triaged"},
    "triaged": {"in_progress"},
    "in_progress": {"fixed"},
    "fixed": {"retest"},
    "retest": {"in_progress", "closed"},
    "closed": set(),
}


class QAIssueCreate(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=36)
    project_id: str = Field(min_length=1, max_length=36)
    task_id: str = Field(min_length=1, max_length=36)
    title: str = Field(min_length=3, max_length=240)
    description: str = Field(min_length=3, max_length=12000)
    severity: str = Field(default="major", pattern="^(blocker|critical|major|minor|cosmetic)$")
    reproducible_steps: list[str] = Field(default_factory=list, max_length=100)
    expected_result: str = Field(default="", max_length=8000)
    actual_result: str = Field(default="", max_length=8000)
    evidence_references: list[str] = Field(default_factory=list, max_length=100)
    assigned_to_user_id: str | None = Field(default=None, max_length=36)


class QAIssueTransition(BaseModel):
    status: str = Field(pattern="^(triaged|in_progress|fixed|retest|closed)$")
    retest_evaluation_run_id: str | None = Field(default=None, max_length=36)
    note: str = Field(default="", max_length=2000)


class QAIssueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workspace_id: str
    project_id: str
    task_id: str
    title: str
    description: str
    severity: str
    status: str
    reproducible_steps: list
    expected_result: str
    actual_result: str
    evidence_references: list
    assigned_to_user_id: str | None
    retest_evaluation_run_id: str | None
    retest_evidence_trust: str | None
    fixed_at: datetime | None
    closed_at: datetime | None
    closed_by_user_id: str | None
    created_by_user_id: str
    created_at: datetime
    updated_at: datetime


def _authorize(org_id: str, workspace_id: str, p: Principal, db: Session, *, write: bool):
    role = require_membership(org_id, p, db)
    allowed = QA_WRITERS if write else QA_READERS
    if role not in allowed and not has_founder_authority(db, org_id, p.user.id):
        from app.auth import require_role
        require_role(role, allowed)
    require_workspace_access_from_context(org_id, workspace_id, db)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


@router.post("/issues", response_model=QAIssueOut, status_code=201)
def create_qa_issue(
    org_id: str,
    body: QAIssueCreate,
    db: Session = Depends(get_db),
    p: Principal = Depends(get_principal),
):
    _authorize(org_id, body.workspace_id, p, db, write=True)
    project = db.query(Project).filter_by(
        id=body.project_id, org_id=org_id, workspace_id=body.workspace_id,
    ).first()
    if project is None:
        raise HTTPException(404, "Project not found in this workspace")

    task = db.query(Task).filter_by(
        id=body.task_id, org_id=org_id, workspace_id=body.workspace_id,
    ).first()
    if task is None:
        raise HTTPException(404, "Task not found in this workspace")

    if task.milestone_id:
        milestone = db.query(Milestone).filter_by(
            id=task.milestone_id, org_id=org_id, workspace_id=body.workspace_id,
        ).first()
        if milestone is None or milestone.project_id != body.project_id:
            raise HTTPException(409, "Task milestone does not belong to the selected project")

    if body.assigned_to_user_id:
        from app.models import Membership
        assigned_member = db.query(Membership).filter_by(
            org_id=org_id, user_id=body.assigned_to_user_id,
        ).first()
        if assigned_member is None:
            raise HTTPException(404, "Assignee is not a member of this organization")

    issue = QAIssue(
        org_id=org_id,
        workspace_id=body.workspace_id,
        project_id=body.project_id,
        task_id=body.task_id,
        title=body.title,
        description=body.description,
        severity=body.severity,
        reproducible_steps=body.reproducible_steps,
        expected_result=body.expected_result,
        actual_result=body.actual_result,
        evidence_references=body.evidence_references,
        assigned_to_user_id=body.assigned_to_user_id,
        created_by_user_id=p.user.id,
    )
    db.add(issue)
    db.flush()
    record_event(
        db, org_id, p.user.id, "qa_issue.created", "qa_issue",
        issue.id, body.workspace_id,
        {"project_id": issue.project_id, "task_id": issue.task_id,
         "severity": issue.severity, "status": issue.status},
    )
    db.commit()
    db.refresh(issue)
    return issue


@router.get("/issues", response_model=list[QAIssueOut])
def list_qa_issues(
    org_id: str,
    workspace_id: str = Query(min_length=1),
    status: str | None = None,
    severity: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    p: Principal = Depends(get_principal),
):
    _authorize(org_id, workspace_id, p, db, write=False)
    query = db.query(QAIssue).filter_by(org_id=org_id, workspace_id=workspace_id)
    if status:
        if status not in {"open", "triaged", "in_progress", "fixed", "retest", "closed"}:
            raise HTTPException(422, "Invalid QA issue status")
        query = query.filter(QAIssue.status == status)
    if severity:
        if severity not in VALID_SEVERITIES:
            raise HTTPException(422, "Invalid QA issue severity")
        query = query.filter(QAIssue.severity == severity)
    return query.order_by(QAIssue.updated_at.desc()).limit(limit).all()


@router.patch("/issues/{issue_id}/transition", response_model=QAIssueOut)
def transition_qa_issue(
    org_id: str,
    issue_id: str,
    body: QAIssueTransition,
    workspace_id: str = Query(min_length=1),
    db: Session = Depends(get_db),
    p: Principal = Depends(get_principal),
):
    _authorize(org_id, workspace_id, p, db, write=True)
    issue = db.query(QAIssue).filter_by(
        id=issue_id, org_id=org_id, workspace_id=workspace_id,
    ).with_for_update().first()
    if issue is None:
        raise HTTPException(404, "QA issue not found")

    previous = issue.status
    if body.status not in TRANSITIONS.get(previous, set()):
        raise HTTPException(409, f"Invalid QA issue transition: {previous} -> {body.status}")

    evaluation = None
    if body.status == "closed":
        if previous != "retest":
            raise HTTPException(409, "A QA issue must complete the retest stage before closure")
        if not body.retest_evaluation_run_id:
            raise HTTPException(422, "A passing task-linked evaluation run is required to close this issue")
        evaluation = db.query(EvaluationRun).filter_by(
            id=body.retest_evaluation_run_id,
            org_id=org_id,
            workspace_id=workspace_id,
        ).first()
        if evaluation is None:
            raise HTTPException(404, "Retest evaluation not found in this workspace")
        if evaluation.task_id != issue.task_id:
            raise HTTPException(409, "Retest evaluation must reference the QA issue's task")
        if not evaluation.passed:
            raise HTTPException(409, "A failed evaluation cannot close a QA issue")
        if issue.fixed_at is None or _utc(evaluation.created_at) < _utc(issue.fixed_at):
            raise HTTPException(409, "Retest evaluation must be created after the issue was marked fixed")
    elif previous == "retest" and body.status == "in_progress" and body.retest_evaluation_run_id:
        evaluation = db.query(EvaluationRun).filter_by(
            id=body.retest_evaluation_run_id,
            org_id=org_id,
            workspace_id=workspace_id,
        ).first()
        if evaluation is None:
            raise HTTPException(404, "Retest evaluation not found in this workspace")
        if evaluation.task_id != issue.task_id:
            raise HTTPException(409, "Retest evaluation must reference the QA issue's task")
        if evaluation.passed:
            raise HTTPException(409, "A passing retest should close the issue, not reopen it")
        if issue.fixed_at is None or _utc(evaluation.created_at) < _utc(issue.fixed_at):
            raise HTTPException(409, "Retest evaluation must be created after the issue was marked fixed")
    elif body.retest_evaluation_run_id is not None:
        raise HTTPException(422, "Retest evaluation can only be attached during closure or failed-retest rework")

    now = datetime.now(timezone.utc)
    issue.status = body.status
    issue.updated_at = now
    if body.status == "fixed":
        issue.fixed_at = now
    elif body.status == "in_progress" and previous == "retest":
        issue.fixed_at = None
    if body.status == "closed":
        issue.retest_evaluation_run_id = evaluation.id
        issue.retest_evidence_trust = evaluation.evidence_trust
        issue.closed_at = now
        issue.closed_by_user_id = p.user.id

    record_event(
        db, org_id, p.user.id, "qa_issue.status_changed", "qa_issue",
        issue.id, workspace_id,
        {"from_status": previous, "to_status": issue.status,
         "retest_evaluation_run_id": evaluation.id if evaluation else None,
         "retest_evidence_trust": evaluation.evidence_trust if evaluation else None,
         "note": body.note},
    )
    db.commit()
    db.refresh(issue)
    return issue
