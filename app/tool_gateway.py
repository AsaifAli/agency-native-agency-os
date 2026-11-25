"""In-process service entry point shared by HTTP and Managed Agent custom tools."""
import hashlib
import json
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.audit import record_event
from app.data_protection import DataProtectionBlocked, protect_untrusted_payload
from app.machine_identity import MachinePrincipal, authorize_tool_session
from app.security_models import AgentSession, ToolInvocation
from app.tool_registry import execute_tool, get_tool, validate_tool_input, validate_tool_output


def invoke_registered_tool(
    db: Session,
    principal: MachinePrincipal,
    *,
    session_id: str,
    tool_key: str,
    payload: dict,
    idempotency_key: str,
) -> dict:
    """Authorize, sanitize, execute and persist one allowlisted tool invocation.

    The caller owns transaction rollback on error. Success is committed here so
    provider callbacks and HTTP callers share exactly the same durable behavior.
    """
    if not isinstance(idempotency_key, str) or not 8 <= len(idempotency_key) <= 160:
        raise HTTPException(422, "Invalid idempotency key")
    spec = get_tool(tool_key)
    if spec is None:
        raise HTTPException(404, "Tool is not registered")
    if spec.requires_approval:
        raise HTTPException(403, "Tool requires an approval adapter that is not enabled")
    identity = principal.identity
    session = db.query(AgentSession).filter_by(
        id=session_id,
        org_id=identity.org_id,
        workspace_id=identity.workspace_id,
        machine_identity_id=identity.id,
    ).first()
    if session is None:
        raise HTTPException(404, "Session not found")
    if session.data_class not in spec.allowed_data_classes:
        raise HTTPException(403, "Tool is not eligible for this session data class")

    try:
        safe_input, input_report = protect_untrusted_payload(payload)
    except DataProtectionBlocked as exc:
        raise HTTPException(422, "Tool input blocked by data-protection policy") from exc
    try:
        validated_input = validate_tool_input(spec, safe_input)
    except ValidationError as exc:
        raise HTTPException(422, "Tool input does not match the registered schema") from exc

    authorize_tool_session(
        db, principal, session_id=session.id, tool_key=spec.key,
        data_class=session.data_class,
    )
    canonical_request = json.dumps(
        {"identity_id": identity.id, "session_id": session.id,
         "tool_key": spec.key, "version": spec.version, "input": validated_input},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    )
    request_hash = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()

    existing = db.query(ToolInvocation).filter_by(
        org_id=identity.org_id,
        workspace_id=identity.workspace_id,
        idempotency_key=idempotency_key,
    ).with_for_update().first()
    if existing is not None:
        if existing.request_hash != request_hash:
            raise HTTPException(409, "Idempotency key was already used for a different tool request")
        return {
            "id": existing.id,
            "tool_key": existing.tool_key,
            "tool_version": existing.tool_version,
            "status": existing.status,
            "result": existing.result,
            "replayed": True,
        }

    try:
        raw_result = execute_tool(
            db, spec, validated_input,
            identity=identity, idempotency_key=idempotency_key,
        )
        validated_result = validate_tool_output(spec, raw_result)
        safe_result, output_report = protect_untrusted_payload(validated_result)
    except DataProtectionBlocked as exc:
        raise HTTPException(502, "Tool output blocked by data-protection policy") from exc
    except Exception as exc:
        # Never expose adapter exception text or request payloads to the caller.
        raise HTTPException(502, "Registered tool execution failed") from exc

    invocation = ToolInvocation(
        org_id=identity.org_id,
        workspace_id=identity.workspace_id,
        machine_identity_id=identity.id,
        session_id=session.id,
        tool_key=spec.key,
        tool_version=spec.version,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        request_payload=validated_input,
        result=safe_result,
        status="succeeded",
        finished_at=datetime.now(timezone.utc),
    )
    db.add(invocation)
    db.flush()
    record_event(
        db, identity.org_id, None, "tool.invocation.succeeded",
        "tool_invocation", invocation.id, identity.workspace_id,
        {
            "machine_identity_id": identity.id,
            "session_id": session.id,
            "tool_key": spec.key,
            "tool_version": spec.version,
            "risk_level": spec.risk_level,
            "data_class": session.data_class,
            "input_redaction_counts": input_report.redaction_counts,
            "output_redaction_counts": output_report.redaction_counts,
            "result_resource_id": safe_result.get("draft_id"),
        },
    )
    db.commit()
    return {
        "id": invocation.id,
        "tool_key": invocation.tool_key,
        "tool_version": invocation.tool_version,
        "status": invocation.status,
        "result": invocation.result,
        "replayed": False,
    }
