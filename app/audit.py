from sqlalchemy.orm import Session
from app.data_protection import DataProtectionBlocked, protect_untrusted_payload
from app.models import AuditEvent


def record_event(
    db: Session,
    org_id: str,
    actor_user_id: str | None,
    event_type: str,
    resource_type: str,
    resource_id: str,
    workspace_id: str | None = None,
    payload: dict | None = None,
):
    # Audit is a durable data surface. Apply the same bounded PII/secret
    # protection here as at provider boundaries so individual routes cannot
    # accidentally persist raw contact details or credentials.
    if payload is not None and not isinstance(payload, dict):
        raise DataProtectionBlocked("INVALID_UNTRUSTED_PAYLOAD")
    safe_payload, _report = protect_untrusted_payload(payload or {})
    event = AuditEvent(
        org_id=org_id,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        payload=safe_payload,
    )
    db.add(event)
    return event
