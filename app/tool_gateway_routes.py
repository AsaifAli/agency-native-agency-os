"""HTTP interface for the shared, policy-enforcing OS Tool Gateway."""
from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.machine_identity import MachinePrincipal, get_machine_principal
from app.tool_gateway import invoke_registered_tool
from app.tool_registry import list_tools

router = APIRouter(tags=["machine-tools"])


class ToolInvokeRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=36)
    input: dict = Field(default_factory=dict)


def _tool_view(spec):
    return {
        "key": spec.key,
        "version": spec.version,
        "description": spec.description,
        "risk_level": spec.risk_level,
        "allowed_data_classes": list(spec.allowed_data_classes),
        "requires_approval": spec.requires_approval,
    }


@router.get("/v1/machine/tools")
def list_machine_tools(
    db: Session = Depends(get_db),
    principal: MachinePrincipal = Depends(get_machine_principal),
):
    identity = principal.identity
    return {
        "tools": [
            _tool_view(spec)
            for spec in list_tools()
            if "tools:invoke" in identity.scopes
            and f"tool:{spec.key}" in identity.scopes
            and any(value in identity.allowed_data_classes for value in spec.allowed_data_classes)
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
