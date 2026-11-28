"""Founder-approved Agent configuration version lifecycle API."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.action_policy import agent_version_resource_id, require_approved_action
from app.agent_registry_schemas import (
    AgentVersionAction,
    AgentVersionCreate,
    AgentVersionOut,
    AgentVersionRollback,
)
from app.agent_registry_service import (
    AgentVersionConflict,
    AgentVersionNotFound,
    activate_agent_version,
    create_agent_version,
    get_agent_version,
    list_agent_versions,
    rollback_agent_version,
)
from app.auth import (
    Principal,
    get_principal,
    require_founder_authority,
    require_membership,
    require_workspace_access_from_context,
)
from app.config import settings
from app.db import get_db
from app.integrations.runtime_registry import is_runtime_available
from app.models import Agent, DataClass
from app.policy import assert_managed_agents_eligible

router = APIRouter(prefix="/v1/orgs/{org_id}/agents", tags=["agent-registry"])


def _agent(db: Session, org_id: str, workspace_id: str, agent_id: str) -> Agent:
    agent = db.query(Agent).filter_by(
        id=agent_id, org_id=org_id, workspace_id=workspace_id,
    ).one_or_none()
    if agent is None:
        raise HTTPException(404, "Agent not found")
    return agent


def _out(version, active_version_id: str | None) -> dict:
    return {
        "id": version.id,
        "agent_id": version.agent_id,
        "version_number": version.version_number,
        "name": version.name,
        "department": version.department,
        "instructions": version.instructions,
        "runtime": version.runtime,
        "data_class": version.data_class.value,
        "runtime_config": version.runtime_config or {},
        "config_sha256": version.config_sha256,
        "change_reason": version.change_reason,
        "created_by": version.created_by,
        "created_at": version.created_at,
        "is_active": version.id == active_version_id,
    }


def _validate_activation_runtime(version) -> None:
    if version.runtime == "mock" and (
        settings.app_env != "test" or not settings.mock_runtime_enabled
    ):
        raise HTTPException(409, "Mock runtime cannot be activated in this environment")
    if not is_runtime_available(version.runtime):
        raise HTTPException(409, "The selected runtime is not configured")
    if version.runtime == "claude_managed_agents":
        try:
            assert_managed_agents_eligible(version.data_class, client_authorized=False)
        except HTTPException as exc:
            raise HTTPException(403, "Managed Agents is not eligible for this data class") from exc


@router.get("/{agent_id}/versions", response_model=list[AgentVersionOut])
def get_agent_versions(
    org_id: str,
    agent_id: str,
    workspace_id: str = Query(min_length=1),
    db: Session = Depends(get_db),
    p: Principal = Depends(get_principal),
):
    require_membership(org_id, p, db)
    require_workspace_access_from_context(org_id, workspace_id, db)
    require_founder_authority(db, org_id, p.user.id)
    agent = _agent(db, org_id, workspace_id, agent_id)
    try:
        versions = list_agent_versions(
            db, org_id=org_id, workspace_id=workspace_id, agent_id=agent_id,
        )
    except AgentVersionNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    return [_out(version, agent.current_version_id) for version in versions]


@router.post("/{agent_id}/versions", response_model=AgentVersionOut, status_code=201)
def create_agent_version_route(
    org_id: str,
    agent_id: str,
    payload: AgentVersionCreate,
    workspace_id: str = Query(min_length=1),
    db: Session = Depends(get_db),
    p: Principal = Depends(get_principal),
):
    require_membership(org_id, p, db)
    require_workspace_access_from_context(org_id, workspace_id, db)
    require_founder_authority(db, org_id, p.user.id)
    agent = _agent(db, org_id, workspace_id, agent_id)
    if payload.runtime == "mock" and (
        settings.app_env != "test" or not settings.mock_runtime_enabled
    ):
        raise HTTPException(422, "Mock runtime is restricted to test environments")
    try:
        version = create_agent_version(
            db,
            org_id=org_id,
            workspace_id=workspace_id,
            agent_id=agent_id,
            name=payload.name,
            department=payload.department,
            instructions=payload.instructions,
            runtime=payload.runtime,
            data_class=DataClass(payload.data_class),
            runtime_config=payload.runtime_config,
            change_reason=payload.change_reason,
            created_by=p.user.id,
        )
        db.commit()
    except AgentVersionNotFound as exc:
        db.rollback()
        raise HTTPException(404, str(exc)) from exc
    except (AgentVersionConflict, ValueError) as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
    return _out(version, agent.current_version_id)


@router.post("/{agent_id}/versions/{version_id}/activate", response_model=AgentVersionOut)
def activate_agent_version_route(
    org_id: str,
    agent_id: str,
    version_id: str,
    payload: AgentVersionAction,
    workspace_id: str = Query(min_length=1),
    db: Session = Depends(get_db),
    p: Principal = Depends(get_principal),
):
    require_membership(org_id, p, db)
    require_workspace_access_from_context(org_id, workspace_id, db)
    require_founder_authority(db, org_id, p.user.id)
    agent = _agent(db, org_id, workspace_id, agent_id)
    try:
        version = get_agent_version(
            db, org_id=org_id, workspace_id=workspace_id,
            agent_id=agent_id, version_id=version_id,
        )
    except AgentVersionNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    _validate_activation_runtime(version)
    expected = {
        "operation": "activate",
        "agent_id": agent_id,
        "version_id": version.id,
        "config_sha256": version.config_sha256,
    }
    require_approved_action(
        db,
        approval_id=payload.approval_id,
        org_id=org_id,
        workspace_id=workspace_id,
        action_type="security.permission.change",
        resource_id=agent_version_resource_id(workspace_id, agent_id, version.id, "activate"),
        actor_user_id=p.user.id,
        expected_request_payload=expected,
    )
    try:
        activated = activate_agent_version(
            db, org_id=org_id, workspace_id=workspace_id,
            agent_id=agent_id, version_id=version.id,
            actor_user_id=p.user.id,
        )
        db.commit()
    except (AgentVersionNotFound, AgentVersionConflict) as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    return _out(activated, agent.current_version_id)


@router.post("/{agent_id}/versions/{version_id}/rollback", response_model=AgentVersionOut)
def rollback_agent_version_route(
    org_id: str,
    agent_id: str,
    version_id: str,
    payload: AgentVersionRollback,
    workspace_id: str = Query(min_length=1),
    db: Session = Depends(get_db),
    p: Principal = Depends(get_principal),
):
    require_membership(org_id, p, db)
    require_workspace_access_from_context(org_id, workspace_id, db)
    require_founder_authority(db, org_id, p.user.id)
    agent = _agent(db, org_id, workspace_id, agent_id)
    try:
        source = get_agent_version(
            db, org_id=org_id, workspace_id=workspace_id,
            agent_id=agent_id, version_id=version_id,
        )
    except AgentVersionNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    _validate_activation_runtime(source)
    expected = {
        "operation": "rollback",
        "agent_id": agent_id,
        "source_version_id": source.id,
        "source_config_sha256": source.config_sha256,
        "change_reason": payload.change_reason,
    }
    require_approved_action(
        db,
        approval_id=payload.approval_id,
        org_id=org_id,
        workspace_id=workspace_id,
        action_type="security.permission.change",
        resource_id=agent_version_resource_id(workspace_id, agent_id, source.id, "rollback"),
        actor_user_id=p.user.id,
        expected_request_payload=expected,
    )
    try:
        version = rollback_agent_version(
            db,
            org_id=org_id,
            workspace_id=workspace_id,
            agent_id=agent_id,
            source_version_id=source.id,
            actor_user_id=p.user.id,
            change_reason=payload.change_reason,
        )
        db.commit()
    except (AgentVersionNotFound, AgentVersionConflict, ValueError) as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    return _out(version, agent.current_version_id)
