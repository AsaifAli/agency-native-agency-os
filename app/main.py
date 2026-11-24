
from datetime import datetime, timezone

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db import get_db
from app.config import settings
from app.auth import (
    get_principal,
    require_membership,
    require_role,
    Principal,
    issue_access_token,
)
from app.models import (
    User,
    Workspace,
    Agent,
    Task,
    Approval,
    AuditEvent,
    Role,
    ApprovalStatus,
    EvaluationRun,
)
from app.schemas import (
    WorkspaceCreate,
    WorkspaceOut,
    AgentCreate,
    AgentOut,
    TaskCreate,
    TaskOut,
    ApprovalCreate,
    ApprovalOut,
    ApprovalDecision,
    AuditOut,
    EvaluationCreate,
    EvaluationOut,
    ExecutionCreate,
    ExecutionOut,
)
from app.audit import record_event
from app.policy import assert_managed_agents_eligible
from app.action_policy import MANDATORY_APPROVAL_ACTIONS
from app.evaluation_service import (
    evaluate as evaluate_pack,
    catalog as evaluation_catalog,
)
from app.execution_service import (
    create_execution,
    ResourceNotFound,
    ExecutionConflict,
    AgentNotEnabled,
    PolicyViolation,
)


app = FastAPI(
    title="Agency OS API",
    version="0.1.0",
    description="Founder-controlled Agency OS foundation",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in settings.cors_origins.split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)



@app.post("/v1/auth/dev-token")
def create_dev_token(email: str, db: Session = Depends(get_db)):
    if not settings.dev_auth_enabled or settings.app_env == "production":
        raise HTTPException(404, "Not found")

    user = db.query(User).filter_by(
        email=email.lower(),
        active=True,
    ).first()

    if not user:
        raise HTTPException(401, "Unknown or inactive user")

    return {
        "access_token": issue_access_token(user.email),
        "token_type": "bearer",
        "expires_in": 1800,
    }


@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        ) from exc

    return {
        "status": "ok",
        "service": "agency-os-api",
        "database": "ok",
    }


def workspace_in_org(db: Session, org_id: str, workspace_id: str):
    workspace = db.query(Workspace).filter_by(
        id=workspace_id,
        org_id=org_id,
    ).first()

    if not workspace:
        raise HTTPException(404, "Workspace not found")

    return workspace


# ---------------------------------------------------------------------------
# Workspaces
# ---------------------------------------------------------------------------

@app.get(
    "/v1/orgs/{org_id}/workspaces",
    response_model=list[WorkspaceOut],
)
def list_workspaces(
    org_id: str,
    db: Session = Depends(get_db),
    p: Principal = Depends(get_principal),
):
    require_membership(org_id, p, db)

    return (
        db.query(Workspace)
        .filter_by(org_id=org_id)
        .all()
    )


@app.post(
    "/v1/orgs/{org_id}/workspaces",
    response_model=WorkspaceOut,
    status_code=201,
)
def create_workspace(
    org_id: str,
    body: WorkspaceCreate,
    db: Session = Depends(get_db),
    p: Principal = Depends(get_principal),
):
    role = require_membership(org_id, p, db)
    require_role(role, {Role.owner, Role.admin})

    workspace = Workspace(
        org_id=org_id,
        name=body.name,
    )

    db.add(workspace)
    db.flush()

    record_event(
        db,
        org_id,
        p.user.id,
        "workspace.created",
        "workspace",
        workspace.id,
        workspace.id,
    )

    db.commit()
    db.refresh(workspace)

    return workspace


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

@app.get(
    "/v1/orgs/{org_id}/agents",
    response_model=list[AgentOut],
)
def list_agents(
    org_id: str,
    workspace_id: str,
    db: Session = Depends(get_db),
    p: Principal = Depends(get_principal),
):
    require_membership(org_id, p, db)
    workspace_in_org(db, org_id, workspace_id)

    return (
        db.query(Agent)
        .filter_by(
            org_id=org_id,
            workspace_id=workspace_id,
        )
        .all()
    )


@app.post(
    "/v1/orgs/{org_id}/agents",
    response_model=AgentOut,
    status_code=201,
)
def create_agent(
    org_id: str,
    body: AgentCreate,
    db: Session = Depends(get_db),
    p: Principal = Depends(get_principal),
):
    role = require_membership(org_id, p, db)
    require_role(role, {Role.owner, Role.admin, Role.operator})

    workspace_in_org(db, org_id, body.workspace_id)

    if body.runtime == "claude_managed_agents":
        assert_managed_agents_eligible(
            body.data_class,
            client_authorized=False,
        )

    agent = Agent(
        org_id=org_id,
        workspace_id=body.workspace_id,
        name=body.name,
        department=body.department,
        instructions=body.instructions,
        runtime=body.runtime,
        data_class=body.data_class,
        enabled=False,
    )

    db.add(agent)
    db.flush()

    record_event(
        db,
        org_id,
        p.user.id,
        "agent.created",
        "agent",
        agent.id,
        body.workspace_id,
        {
            "runtime": body.runtime,
            "data_class": body.data_class.value,
        },
    )

    db.commit()
    db.refresh(agent)

    return agent


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@app.get(
    "/v1/orgs/{org_id}/tasks",
    response_model=list[TaskOut],
)
def list_tasks(
    org_id: str,
    workspace_id: str,
    db: Session = Depends(get_db),
    p: Principal = Depends(get_principal),
):
    require_membership(org_id, p, db)
    workspace_in_org(db, org_id, workspace_id)

    return (
        db.query(Task)
        .filter_by(
            org_id=org_id,
            workspace_id=workspace_id,
        )
        .all()
    )


@app.post(
    "/v1/orgs/{org_id}/tasks",
    response_model=TaskOut,
    status_code=201,
)
def create_task(
    org_id: str,
    body: TaskCreate,
    db: Session = Depends(get_db),
    p: Principal = Depends(get_principal),
):
    role = require_membership(org_id, p, db)
    require_role(role, {Role.owner, Role.admin, Role.operator})

    workspace_in_org(db, org_id, body.workspace_id)

    task = Task(
        org_id=org_id,
        workspace_id=body.workspace_id,
        title=body.title,
        description=body.description,
        created_by=p.user.id,
    )

    db.add(task)
    db.flush()

    record_event(
        db,
        org_id,
        p.user.id,
        "task.created",
        "task",
        task.id,
        body.workspace_id,
    )

    db.commit()
    db.refresh(task)

    return task


# ---------------------------------------------------------------------------
# Executions
# ---------------------------------------------------------------------------

@app.post(
    "/v1/orgs/{org_id}/executions",
    response_model=ExecutionOut,
    status_code=201,
)
def create_execution_endpoint(
    org_id: str,
    body: ExecutionCreate,
    db: Session = Depends(get_db),
    p: Principal = Depends(get_principal),
):
    role = require_membership(org_id, p, db)
    require_role(role, {Role.owner, Role.admin, Role.operator})

    try:
        execution = create_execution(
            db,
            org_id=org_id,
            workspace_id=body.workspace_id,
            task_id=body.task_id,
            agent_id=body.agent_id,
            requested_by=p.user.id,
            idempotency_key=body.idempotency_key,
            max_attempts=body.max_attempts,
        )

        db.commit()
        db.refresh(execution)

        return execution

    except ResourceNotFound as exc:
        db.rollback()
        raise HTTPException(404, str(exc)) from exc

    except AgentNotEnabled as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc

    except ExecutionConflict as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc

    except PolicyViolation as exc:
        db.rollback()
        raise HTTPException(403, str(exc)) from exc

    except Exception:
        db.rollback()
        raise


# ---------------------------------------------------------------------------
# Approvals
# ---------------------------------------------------------------------------

@app.get(
    "/v1/orgs/{org_id}/approvals",
    response_model=list[ApprovalOut],
)
def list_approvals(
    org_id: str,
    workspace_id: str | None = None,
    db: Session = Depends(get_db),
    p: Principal = Depends(get_principal),
):
    role = require_membership(org_id, p, db)
    require_role(
        role,
        {Role.owner, Role.admin, Role.operator, Role.reviewer},
    )

    query = db.query(Approval).filter_by(org_id=org_id)

    if workspace_id:
        workspace_in_org(db, org_id, workspace_id)
        query = query.filter_by(workspace_id=workspace_id)

    return (
        query
        .order_by(Approval.created_at.desc())
        .limit(500)
        .all()
    )


@app.post(
    "/v1/orgs/{org_id}/approvals",
    response_model=ApprovalOut,
    status_code=201,
)
def create_approval(
    org_id: str,
    body: ApprovalCreate,
    db: Session = Depends(get_db),
    p: Principal = Depends(get_principal),
):
    role = require_membership(org_id, p, db)
    require_role(role, {Role.owner, Role.admin, Role.operator})

    if body.action_type not in MANDATORY_APPROVAL_ACTIONS:
        raise HTTPException(
            400,
            "Action type is not in the mandatory approval policy registry",
        )

    workspace_in_org(db, org_id, body.workspace_id)

    existing = db.query(Approval).filter_by(
        org_id=org_id,
        idempotency_key=body.idempotency_key,
    ).first()

    if existing:
        if (
            existing.action_type != body.action_type
            or existing.resource_id != body.resource_id
            or existing.workspace_id != body.workspace_id
        ):
            raise HTTPException(
                409,
                "Idempotency key was already used for a different approval request",
            )

        return existing

    approval = Approval(
        org_id=org_id,
        workspace_id=body.workspace_id,
        action_type=body.action_type,
        resource_id=body.resource_id,
        idempotency_key=body.idempotency_key,
        request_payload=body.request_payload,
        requested_by=p.user.id,
    )

    db.add(approval)
    db.flush()

    record_event(
        db,
        org_id,
        p.user.id,
        "approval.requested",
        "approval",
        approval.id,
        body.workspace_id,
        {
            "action_type": body.action_type,
            "resource_id": body.resource_id,
        },
    )

    db.commit()
    db.refresh(approval)

    return approval


@app.post(
    "/v1/orgs/{org_id}/approvals/{approval_id}/decision",
)
def decide_approval(
    org_id: str,
    approval_id: str,
    body: ApprovalDecision,
    db: Session = Depends(get_db),
    p: Principal = Depends(get_principal),
):
    role = require_membership(org_id, p, db)
    require_role(role, {Role.owner})

    if body.decision == ApprovalStatus.pending:
        raise HTTPException(
            400,
            "Decision must be approved or rejected",
        )

    approval = (
        db.query(Approval)
        .filter_by(
            id=approval_id,
            org_id=org_id,
        )
        .with_for_update()
        .first()
    )

    if not approval:
        raise HTTPException(404, "Approval not found")

    if approval.status != ApprovalStatus.pending:
        raise HTTPException(409, "Approval already decided")

    if approval.requested_by == p.user.id:
        raise HTTPException(
            403,
            "Requester cannot approve their own request",
        )

    approval.status = body.decision
    approval.decided_by = p.user.id
    approval.decision_note = body.note
    approval.decided_at = datetime.now(timezone.utc)

    record_event(
        db,
        org_id,
        p.user.id,
        "approval.decided",
        "approval",
        approval.id,
        approval.workspace_id,
        {
            "decision": body.decision.value,
        },
    )

    db.commit()

    return {
        "id": approval.id,
        "status": approval.status.value,
    }


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

@app.get(
    "/v1/orgs/{org_id}/audit",
    response_model=list[AuditOut],
)
def list_audit(
    org_id: str,
    limit: int = 100,
    db: Session = Depends(get_db),
    p: Principal = Depends(get_principal),
):
    role = require_membership(org_id, p, db)
    require_role(role, {Role.owner, Role.admin, Role.reviewer})

    return (
        db.query(AuditEvent)
        .filter_by(org_id=org_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(min(limit, 500))
        .all()
    )


# ---------------------------------------------------------------------------
# Evaluation Harness integration
# ---------------------------------------------------------------------------

@app.get("/v1/evaluations/packs")
def list_evaluation_packs(
    org_id: str,
    db: Session = Depends(get_db),
    p: Principal = Depends(get_principal),
):
    require_membership(org_id, p, db)

    return {
        "packs": evaluation_catalog(),
    }


@app.post(
    "/v1/orgs/{org_id}/evaluations",
    response_model=EvaluationOut,
    status_code=201,
)
def create_evaluation(
    org_id: str,
    body: EvaluationCreate,
    db: Session = Depends(get_db),
    p: Principal = Depends(get_principal),
):
    role = require_membership(org_id, p, db)
    require_role(
        role,
        {Role.owner, Role.admin, Role.operator, Role.reviewer},
    )

    workspace_in_org(db, org_id, body.workspace_id)

    if body.task_id:
        task = db.query(Task).filter_by(
            id=body.task_id,
            org_id=org_id,
            workspace_id=body.workspace_id,
        ).first()

        if not task:
            raise HTTPException(404, "Task not found")

    try:
        result = evaluate_pack(
            body.pack_name,
            body.expected,
            body.actual,
        )
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc

    run = EvaluationRun(
        org_id=org_id,
        workspace_id=body.workspace_id,
        task_id=body.task_id,
        pack_name=result["pack_name"],
        score=result["score"],
        passed=result["passed"],
        metrics=result["metrics"],
        gate_results=result["gate_results"],
        created_by=p.user.id,
    )

    db.add(run)
    db.flush()

    record_event(
        db,
        org_id,
        p.user.id,
        "evaluation.completed",
        "evaluation",
        run.id,
        body.workspace_id,
        {
            "pack": run.pack_name,
            "score": run.score,
            "passed": run.passed,
        },
    )

    db.commit()
    db.refresh(run)

    return run


@app.get(
    "/v1/orgs/{org_id}/evaluations",
    response_model=list[EvaluationOut],
)
def list_evaluations(
    org_id: str,
    workspace_id: str,
    db: Session = Depends(get_db),
    p: Principal = Depends(get_principal),
):
    role = require_membership(org_id, p, db)
    require_role(
        role,
        {Role.owner, Role.admin, Role.operator, Role.reviewer},
    )

    workspace_in_org(db, org_id, workspace_id)

    return (
        db.query(EvaluationRun)
        .filter_by(
            org_id=org_id,
            workspace_id=workspace_id,
        )
        .order_by(EvaluationRun.created_at.desc())
        .limit(500)
        .all()
    )


# Revenue and Delivery API module installed by Agency OS bundle.
from app.domain_routes import router as revenue_delivery_router
app.include_router(revenue_delivery_router)
