"""Machine-authenticated HTTP surface for the OS-owned Tool Gateway."""
from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.machine_identity import MachinePrincipal, get_machine_principal
from app.tool_gateway import invoke_registered_tool
from app.tool_registry import list_tools
from app.workforce_models import WorkforceCapability, WorkforceMember

router = APIRouter(tags=["machine-tools"])


class ToolInvokeRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=36)
    input: dict = Field(default_factory=dict)


def _agent_authorized_tool_data_classes(
    db: Session, identity
) -> dict[str, set[str]] | None:
    """Return per-tool data classes granted to an agent.

    None means a non-agent machine identity. Discovery is filtered by the
    workforce grant as well as the machine credential. Invocation still
    performs the authoritative locked authorization check in the shared
    Tool Gateway.
    """
    if identity.subject_type != "agent":
        return None

    member = (
        db.query(WorkforceMember)
        .filter_by(
            org_id=identity.org_id,
            workspace_id=identity.workspace_id,
            agent_id=identity.subject_id,
        )
        .first()
    )
    if member is None or member.status != "active" or member.is_founder_reserved:
        return {}

    scope_rank = {"self": 0, "team": 1, "workspace": 2}
    grants = (
        db.query(WorkforceCapability)
        .filter_by(
            org_id=identity.org_id,
            workspace_id=identity.workspace_id,
            member_id=member.id,
            enabled=True,
        )
        .all()
    )
    allowed: dict[str, set[str]] = {}
    for spec in list_tools():
        if spec.minimum_scope not in scope_rank:
            continue
        data_classes = {
            data_class
            for grant in grants
            if (
                spec.key in (grant.tool_allowlist or [])
                and spec.required_action in (grant.allowed_actions or [])
                and grant.scope in scope_rank
                and scope_rank[grant.scope] >= scope_rank[spec.minimum_scope]
            )
            for data_class in set(identity.allowed_data_classes)
            .intersection(spec.allowed_data_classes)
            .intersection(grant.allowed_data_classes or [])
        }
        if data_classes:
            allowed[spec.key] = data_classes
    return allowed


def _tool_view(spec, identity_allowed_data_classes: list[str]):
    return {
        "key": spec.key,
        "version": spec.version,
        "description": spec.description,
        "risk_level": spec.risk_level,
        "required_action": spec.required_action,
        "minimum_scope": spec.minimum_scope,
        "allowed_data_classes": sorted(
            set(spec.allowed_data_classes).intersection(identity_allowed_data_classes)
        ),
        "requires_approval": spec.requires_approval,
    }


@router.get("/v1/machine/tools")
def list_machine_tools(
    db: Session = Depends(get_db),
    principal: MachinePrincipal = Depends(get_machine_principal),
):
    identity = principal.identity
    agent_tool_data_classes = _agent_authorized_tool_data_classes(db, identity)
    return {
        "tools": [
            _tool_view(
                spec,
                identity.allowed_data_classes
                if agent_tool_data_classes is None
                else list(agent_tool_data_classes[spec.key]),
            )
            for spec in list_tools()
            if "tools:invoke" in identity.scopes
            and f"tool:{spec.key}" in identity.scopes
            and any(value in identity.allowed_data_classes for value in spec.allowed_data_classes)
            and (
                agent_tool_data_classes is None
                or spec.key in agent_tool_data_classes
            )
        ]
    }


@router.post("/v1/machine/tools/{tool_key}/invoke")
def invoke_machine_tool(
    tool_key: str,
    body: ToolInvokeRequest,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=160),
    db: Session = Depends(get_db),
    principal: MachinePrincipal = Depends(get_machine_principal),
):
    return invoke_registered_tool(
        db,
        principal,
        session_id=body.session_id,
        tool_key=tool_key,
        payload=body.input,
        idempotency_key=idempotency_key,
    )
