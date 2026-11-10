from sqlalchemy.orm import Session
from app.models import AuditEvent

def record_event(db: Session, org_id: str, actor_user_id: str | None, event_type: str,
                 resource_type: str, resource_id: str, workspace_id: str | None = None,
                 payload: dict | None = None):
    event = AuditEvent(org_id=org_id, workspace_id=workspace_id, actor_user_id=actor_user_id,
                       event_type=event_type, resource_type=resource_type,
                       resource_id=resource_id, payload=payload or {})
    db.add(event)
    return event
