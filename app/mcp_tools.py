"""MCP tool discovery and dispatch, independent of the transport SDK."""
from __future__ import annotations

import hashlib
from typing import Iterable

from sqlalchemy.orm import Session

from app.mcp_auth import SessionCredentialContext
from app.session_credentials import load_active_session_context
from app.tool_gateway import invoke_registered_tool
from app.tool_registry import list_tools


def list_session_tools(
    db: Session,
    context: SessionCredentialContext,
    *,
    enabled_tool_keys: Iterable[str],
) -> list[dict]:
    principal, session = load_active_session_context(db, context)
    identity = principal.identity
    enabled = set(enabled_tool_keys)
    tools = []
    for spec in list_tools():
        if (
            spec.key not in enabled
            or spec.requires_approval
            or "tools:invoke" not in identity.scopes
            or f"tool:{spec.key}" not in identity.scopes
            or session.data_class not in spec.allowed_data_classes
            or session.data_class not in identity.allowed_data_classes
        ):
            continue
        tools.append({
            "name": spec.key,
            "description": spec.description,
            "input_schema": spec.input_model.model_json_schema(),
        })
    return tools


def call_session_tool(
    db: Session,
    context: SessionCredentialContext,
    *,
    tool_name: str,
    arguments: dict,
    request_id: str | int,
    enabled_tool_keys: Iterable[str],
    max_calls_per_session: int = 50,
) -> dict:
    principal, session = load_active_session_context(db, context)
    request_identity = f"{session.id}:{request_id}:{tool_name}"
    idempotency_key = "mcp_" + hashlib.sha256(request_identity.encode("utf-8")).hexdigest()
    return invoke_registered_tool(
        db,
        principal,
        session_id=session.id,
        tool_key=tool_name,
        payload=arguments,
        idempotency_key=idempotency_key,
        max_calls_per_session=max_calls_per_session,
        allowed_tool_keys=set(enabled_tool_keys),
    )
