"""In-process service entry point shared by HTTP and Managed Agent custom tools."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import NoReturn

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.audit import record_event
from app.data_protection import DataProtectionBlocked, protect_untrusted_payload
from app.machine_identity import MachinePrincipal, authorize_tool_session
from app.security_models import AgentSession, ToolInvocation
from app.workforce_models import WorkforceCapability, WorkforceMember
from app.tool_registry import (
    execute_tool,
    get_tool,
    validate_tool_input,
    validate_tool_output,
)


def _deny(
    db: Session,
    *,
    org_id: str,
    workspace_id: str,
    identity_id: str,
    tool_key: str,
    reason_code: str,
    status_code: int,
    message: str,
    redaction_counts: dict | None = None,
) -> NoReturn:
    """Roll back protected work, persist a minimal denial audit, then reject."""
    db.rollback()
    safe_tool_key = (
        tool_key[:100]
        if isinstance(tool_key, str) and re.fullmatch(r"[a-z0-9_.-]{1,100}", tool_key)
        else "unknown"
    )
    record_event(
        db,
        org_id,
        None,
        "tool.invocation.denied",
        "machine_identity",
        identity_id,
        workspace_id,
        {
            "machine_identity_id": identity_id,
            "tool_key": safe_tool_key,
            "reason_code": reason_code,
            "redaction_counts": redaction_counts or {},
        },
    )
    db.commit()
    raise HTTPException(status_code, message)


def invoke_registered_tool(
    db: Session,
    principal: MachinePrincipal,
    *,
    session_id: str,
    tool_key: str,
    payload: dict,
    idempotency_key: str,
    idempotency_context: dict | None = None,
    allowed_tool_keys: set[str] | frozenset[str] | None = None,
    max_calls_per_session: int | None = None,
) -> dict:
    """Authorize, protect, validate, execute and persist one registered tool call."""
    identity = principal.identity
    org_id = identity.org_id
    workspace_id = identity.workspace_id
    identity_id = identity.id

    if not isinstance(idempotency_key, str) or not 8 <= len(idempotency_key) <= 160:
        _deny(
            db, org_id=org_id, workspace_id=workspace_id, identity_id=identity_id,
            tool_key=tool_key, reason_code="INVALID_IDEMPOTENCY_KEY",
            status_code=422, message="Tool invocation was denied by OS policy.",
        )

    if allowed_tool_keys is not None:
        if not isinstance(allowed_tool_keys, (set, frozenset)) or any(
            not isinstance(value, str)
            or not re.fullmatch(r"[a-z0-9_.-]{1,100}", value)
            for value in allowed_tool_keys
        ):
            _deny(
                db, org_id=org_id, workspace_id=workspace_id, identity_id=identity_id,
                tool_key=tool_key, reason_code="INVALID_SESSION_TOOL_ALLOWLIST",
                status_code=422, message="Tool invocation was denied by OS policy.",
            )
        if tool_key not in allowed_tool_keys:
            _deny(
                db, org_id=org_id, workspace_id=workspace_id, identity_id=identity_id,
                tool_key=tool_key, reason_code="SESSION_TOOL_NOT_ALLOWED",
                status_code=403, message="Tool invocation was denied by OS policy.",
            )

    if max_calls_per_session is not None and (
        isinstance(max_calls_per_session, bool)
        or not isinstance(max_calls_per_session, int)
        or not 1 <= max_calls_per_session <= 10000
    ):
        _deny(
            db, org_id=org_id, workspace_id=workspace_id, identity_id=identity_id,
            tool_key=tool_key, reason_code="INVALID_SESSION_CALL_LIMIT",
            status_code=422, message="Tool invocation was denied by OS policy.",
        )

    spec = get_tool(tool_key)
    if spec is None:
        _deny(
            db, org_id=org_id, workspace_id=workspace_id, identity_id=identity_id,
            tool_key=tool_key, reason_code="TOOL_NOT_REGISTERED",
            status_code=404, message="Tool invocation was denied by OS policy.",
        )
    if spec.requires_approval:
        _deny(
            db, org_id=org_id, workspace_id=workspace_id, identity_id=identity_id,
            tool_key=spec.key, reason_code="APPROVAL_ADAPTER_REQUIRED",
            status_code=403, message="Tool invocation was denied by OS policy.",
        )

    session = (
        db.query(AgentSession)
        .filter_by(
            id=session_id,
            org_id=identity.org_id,
            workspace_id=identity.workspace_id,
            machine_identity_id=identity.id,
        )
        .first()
    )
    if session is None:
        _deny(
            db, org_id=org_id, workspace_id=workspace_id, identity_id=identity_id,
            tool_key=spec.key, reason_code="SESSION_NOT_FOUND",
            status_code=404, message="Tool invocation was denied by OS policy.",
        )
    if session.data_class not in spec.allowed_data_classes:
        _deny(
            db, org_id=org_id, workspace_id=workspace_id, identity_id=identity_id,
            tool_key=spec.key, reason_code="DATA_CLASS_NOT_ALLOWED",
            status_code=403, message="Tool invocation was denied by OS policy.",
        )

    try:
        safe_input, input_report = protect_untrusted_payload(payload)
    except DataProtectionBlocked:
        _deny(
            db, org_id=org_id, workspace_id=workspace_id, identity_id=identity_id,
            tool_key=spec.key, reason_code="INPUT_DATA_PROTECTION_BLOCKED",
            status_code=422, message="Tool input blocked by data-protection policy.",
        )

    try:
        validated_input = validate_tool_input(spec, safe_input)
    except ValidationError:
        _deny(
            db, org_id=org_id, workspace_id=workspace_id, identity_id=identity_id,
            tool_key=spec.key, reason_code="INPUT_SCHEMA_INVALID",
            status_code=422, message="Tool invocation was denied by OS policy.",
            redaction_counts=input_report.redaction_counts,
        )

    try:
        authorize_tool_session(
            db,
            principal,
            session_id=session.id,
            tool_key=spec.key,
            data_class=session.data_class,
        )
        # Claude agent identities must also hold a live, founder-enabled workforce
        # grant for this exact tool, action and data class. Machine scopes alone
        # are not an organizational capability grant.
        if identity.subject_type == "agent":
            member = (
                db.query(WorkforceMember)
                .filter_by(
                    org_id=identity.org_id,
                    workspace_id=identity.workspace_id,
                    agent_id=identity.subject_id,
                )
                .with_for_update()
                .one_or_none()
            )
            if member is None or member.status != "active" or member.is_founder_reserved:
                raise HTTPException(403, "Workforce member is not active")
            scope_rank = {"self": 0, "team": 1, "workspace": 2}
            grants = (
                db.query(WorkforceCapability)
                .filter_by(
                    org_id=identity.org_id,
                    workspace_id=identity.workspace_id,
                    member_id=member.id,
                    enabled=True,
                )
                .with_for_update()
                .all()
            )
            eligible = any(
                spec.key in (grant.tool_allowlist or [])
                and spec.required_action in (grant.allowed_actions or [])
                and session.data_class in (grant.allowed_data_classes or [])
                and grant.scope in scope_rank
                and scope_rank[grant.scope] >= scope_rank[spec.minimum_scope]
                for grant in grants
            )
            if not eligible:
                raise HTTPException(403, "No enabled workforce capability authorizes this tool")
    except HTTPException:
        _deny(
            db, org_id=org_id, workspace_id=workspace_id, identity_id=identity_id,
            tool_key=spec.key, reason_code="AUTHORIZATION_DENIED",
            status_code=403, message="Tool invocation was denied by OS policy.",
        )

    canonical = json.dumps(
        {
            "identity_id": identity.id,
            "session_id": session.id if idempotency_context is None else None,
            "idempotency_context": idempotency_context or {},
            "tool_key": spec.key,
            "version": spec.version,
            "input": validated_input,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    request_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    existing = (
        db.query(ToolInvocation)
        .filter_by(
            org_id=identity.org_id,
            workspace_id=identity.workspace_id,
            idempotency_key=idempotency_key,
        )
        .with_for_update()
        .first()
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            _deny(
                db, org_id=org_id, workspace_id=workspace_id, identity_id=identity_id,
                tool_key=spec.key, reason_code="IDEMPOTENCY_CONFLICT",
                status_code=409, message="Tool invocation was denied by OS policy.",
            )
        if existing.payload_purged_at is not None:
            raise HTTPException(
                status_code=410,
                detail="IDEMPOTENCY_RESULT_EXPIRED",
            )
        db.commit()
        return {
            "id": existing.id,
            "tool_key": existing.tool_key,
            "tool_version": existing.tool_version,
            "status": existing.status,
            "result": existing.result,
            "replayed": True,
        }

    # authorize_tool_session locks the AgentSession row, serializing concurrent
    # calls so this persisted-success count cannot be oversubscribed.
    if max_calls_per_session is not None:
        successful_calls = (
            db.query(ToolInvocation.id)
            .filter_by(
                org_id=identity.org_id,
                workspace_id=identity.workspace_id,
                session_id=session.id,
                status="succeeded",
            )
            .count()
        )
        if successful_calls >= max_calls_per_session:
            _deny(
                db, org_id=org_id, workspace_id=workspace_id, identity_id=identity_id,
                tool_key=spec.key, reason_code="SESSION_TOOL_CALL_LIMIT_REACHED",
                status_code=429, message="Tool invocation was denied by OS policy.",
            )

    try:
        raw_result = execute_tool(
            db, spec, validated_input, identity=identity,
            idempotency_key=idempotency_key,
        )
        validated_result = validate_tool_output(spec, raw_result)
        safe_result, output_report = protect_untrusted_payload(
            validated_result,
            trusted_internal_id_keys={"draft_id", "lead_id", "research_record_id"},
        )
    except DataProtectionBlocked:
        _deny(
            db, org_id=org_id, workspace_id=workspace_id, identity_id=identity_id,
            tool_key=spec.key, reason_code="OUTPUT_DATA_PROTECTION_BLOCKED",
            status_code=502, message="Tool output blocked by data-protection policy.",
            redaction_counts=input_report.redaction_counts,
        )
    except ValidationError:
        _deny(
            db, org_id=org_id, workspace_id=workspace_id, identity_id=identity_id,
            tool_key=spec.key, reason_code="OUTPUT_SCHEMA_INVALID",
            status_code=502, message="Tool invocation was denied by OS policy.",
            redaction_counts=input_report.redaction_counts,
        )
    except Exception:
        _deny(
            db, org_id=org_id, workspace_id=workspace_id, identity_id=identity_id,
            tool_key=spec.key, reason_code="TOOL_EXECUTION_FAILED",
            status_code=502, message="Tool invocation was denied by OS policy.",
            redaction_counts=input_report.redaction_counts,
        )

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
        db,
        identity.org_id,
        None,
        "tool.invocation.succeeded",
        "tool_invocation",
        invocation.id,
        identity.workspace_id,
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
