"""Workspace-authorized execution controls."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import (
    Principal,
    get_principal,
    has_founder_authority,
    require_membership,
    require_role,
    require_workspace_access_from_context,
)
from app.db import get_db
from app.models import Role
from app.execution_controls import (
    ExecutionNotFound,
    InvalidExecutionState,
    request_execution_cancel,
    request_execution_pause,
    resume_execution,
)

router = APIRouter()


@router.post("/v1/orgs/{org_id}/executions/{execution_id}/cancel")
def cancel_execution_endpoint(
    org_id: str,
    execution_id: str,
    workspace_id: str,
    db: Session = Depends(get_db),
    p: Principal = Depends(get_principal),
):
    """Request cancellation of an execution in an exactly authorized workspace."""
    role = require_membership(org_id, p, db)
    if role not in {Role.owner, Role.admin, Role.operator} and not has_founder_authority(db, org_id, p.user.id):
        require_role(role, {Role.owner, Role.admin, Role.operator})
    require_workspace_access_from_context(org_id, workspace_id, db)

    try:
        execution = request_execution_cancel(
            db,
            execution_id=execution_id,
            org_id=org_id,
            workspace_id=workspace_id,
            actor_user_id=p.user.id,
        )
        db.commit()
        db.refresh(execution)
        return {
            "execution_id": execution.id,
            "status": execution.status.value,
            "error_code": execution.error_code,
            "error_message": execution.error_message,
            "control_request": (execution.request_metadata or {}).get("control_request"),
        }
    except ExecutionNotFound as exc:
        db.rollback()
        raise HTTPException(404, "Execution not found") from exc
    except InvalidExecutionState as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    except Exception:
        db.rollback()
        raise



def _authorize_execution_control(org_id: str, workspace_id: str, db: Session, p: Principal) -> None:
    role = require_membership(org_id, p, db)
    if role not in {Role.owner, Role.admin, Role.operator} and not has_founder_authority(db, org_id, p.user.id):
        require_role(role, {Role.owner, Role.admin, Role.operator})
    require_workspace_access_from_context(org_id, workspace_id, db)


def _control_response(execution):
    return {
        "execution_id": execution.id,
        "status": execution.status.value,
        "error_code": execution.error_code,
        "error_message": execution.error_message,
        "control_request": (execution.request_metadata or {}).get("control_request"),
    }


@router.post("/v1/orgs/{org_id}/executions/{execution_id}/pause")
def pause_execution_endpoint(
    org_id: str, execution_id: str, workspace_id: str,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    _authorize_execution_control(org_id, workspace_id, db, p)
    try:
        execution = request_execution_pause(
            db, execution_id=execution_id, org_id=org_id,
            workspace_id=workspace_id, actor_user_id=p.user.id,
        )
        db.commit()
        db.refresh(execution)
        return _control_response(execution)
    except ExecutionNotFound as exc:
        db.rollback()
        raise HTTPException(404, "Execution not found") from exc
    except InvalidExecutionState as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.post("/v1/orgs/{org_id}/executions/{execution_id}/resume")
def resume_execution_endpoint(
    org_id: str, execution_id: str, workspace_id: str,
    db: Session = Depends(get_db), p: Principal = Depends(get_principal),
):
    _authorize_execution_control(org_id, workspace_id, db, p)
    try:
        execution = resume_execution(
            db, execution_id=execution_id, org_id=org_id,
            workspace_id=workspace_id, actor_user_id=p.user.id,
        )
        db.commit()
        db.refresh(execution)
        return _control_response(execution)
    except ExecutionNotFound as exc:
        db.rollback()
        raise HTTPException(404, "Execution not found") from exc
    except InvalidExecutionState as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    except Exception:
        db.rollback()
        raise
