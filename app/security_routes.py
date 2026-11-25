"""Founder-governed machine identity and machine-session API."""
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, Field, field_validator
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import Principal, get_principal, require_founder_authority, require_workspace_access_from_context
from app.audit import record_event
from app.db import get_db
from app.data_protection import DataProtectionBlocked, sanitize_text
from app.machine_identity import (
    ALLOWED_DATA_CLASSES, ALLOWED_SUBJECT_TYPES, MachinePrincipal,
    create_agent_session, get_machine_principal, issue_machine_credential,
)
from app.models import Agent, Workspace
from app.security_models import AgentSession, MachineIdentity

router = APIRouter(tags=["machine-security"])


class MachineIdentityCreate(BaseModel):
    workspace_id: str
    name: str = Field(min_length=2, max_length=160)
    subject_type: str
    subject_id: str = Field(min_length=1, max_length=36)
    scopes: list[str] = Field(default_factory=list, max_length=40)
    allowed_data_classes: list[str] = Field(default_factory=lambda: ["synthetic"], min_length=1, max_length=5)
    ttl_days: int = Field(default=30, ge=1, le=90)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value):
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Machine identity name must contain at least two non-space characters")
        return value

    @field_validator("subject_type")
    @classmethod
    def validate_subject_type(cls, value):
        if value not in ALLOWED_SUBJECT_TYPES:
            raise ValueError("Unsupported machine identity subject type")
        return value

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, values):
        import re
        allowed = {"sessions:create", "tools:invoke"}
        if any(not isinstance(v, str) or not v or len(v) > 120 for v in values):
            raise ValueError("Invalid machine identity scope")
        if len(set(values)) != len(values) or any(
            v not in allowed and not re.fullmatch(r"tool:[a-z0-9_.-]{1,100}", v)
            for v in values
        ):
            raise ValueError("Unsupported or duplicate machine identity scope")
        return values

    @field_validator("allowed_data_classes")
    @classmethod
    def validate_data_classes(cls, values):
        if len(set(values)) != len(values) or any(v not in {"synthetic", "public"} for v in values):
            raise ValueError("Only synthetic and public data grants are currently enabled")
        return values


class MachineSessionCreate(BaseModel):
    purpose: str = Field(min_length=2, max_length=240)
    data_class: str = "synthetic"
    ttl_seconds: int = Field(default=3600, ge=60, le=86400)


@router.post("/v1/orgs/{org_id}/machine-identities", status_code=201)
def create_machine_identity(
    org_id: str,
    body: MachineIdentityCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    require_founder_authority(db, org_id, principal.user.id)
    require_workspace_access_from_context(org_id, body.workspace_id, db)
    if body.subject_type == "agent":
        subject = db.query(Agent).filter_by(id=body.subject_id, org_id=org_id, workspace_id=body.workspace_id).first()
        if subject is None:
            raise HTTPException(404, "Agent not found")
        if not subject.enabled:
            raise HTTPException(409, "Agent must be enabled before provisioning a machine identity")
    raw_secret, digest, _ = issue_machine_credential()
    identity = MachineIdentity(
        org_id=org_id, workspace_id=body.workspace_id, name=body.name.strip(),
        subject_type=body.subject_type, subject_id=body.subject_id,
        token_hash=digest, token_prefix="pending",
        scopes=body.scopes, allowed_data_classes=body.allowed_data_classes,
        expires_at=datetime.now(timezone.utc) + timedelta(days=body.ttl_days),
        created_by_user_id=principal.user.id,
    )
    db.add(identity)
    db.flush()
    identity.token_prefix = f"aos_mi_{identity.id}."
    record_event(
        db, org_id, principal.user.id, "machine_identity.created",
        "machine_identity", identity.id, body.workspace_id,
        {"subject_type": identity.subject_type, "scopes": identity.scopes,
         "allowed_data_classes": identity.allowed_data_classes, "token_prefix": identity.token_prefix},
    )
    db.commit()
    return {
        "id": identity.id, "name": identity.name, "workspace_id": identity.workspace_id,
        "subject_type": identity.subject_type, "subject_id": identity.subject_id,
        "scopes": identity.scopes, "allowed_data_classes": identity.allowed_data_classes,
        "expires_at": identity.expires_at, "token": f"aos_mi_{identity.id}.{raw_secret}",
        "warning": "The credential is shown once. Store it in a secret manager; it cannot be retrieved again.",
    }


@router.post("/v1/orgs/{org_id}/machine-identities/{identity_id}/revoke")
def revoke_machine_identity(
    org_id: str, identity_id: str, workspace_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    require_founder_authority(db, org_id, principal.user.id)
    require_workspace_access_from_context(org_id, workspace_id, db)
    identity = db.query(MachineIdentity).filter_by(
        id=identity_id, org_id=org_id, workspace_id=workspace_id
    ).with_for_update().first()
    if identity is None:
        raise HTTPException(404, "Machine identity not found")
    if identity.revoked_at is None:
        now = datetime.now(timezone.utc)
        identity.revoked_at = now
        db.query(AgentSession).filter_by(machine_identity_id=identity.id, status="active").update(
            {"status": "cancelled", "ended_at": now}, synchronize_session=False
        )
        record_event(db, org_id, principal.user.id, "machine_identity.revoked",
                     "machine_identity", identity.id, identity.workspace_id,
                     {"active_sessions_cancelled": True})
        db.commit()
    return {"id": identity.id, "revoked": True}


@router.post("/v1/machine/sessions", status_code=201)
def create_machine_session(
    body: MachineSessionCreate, db: Session = Depends(get_db),
    principal: MachinePrincipal = Depends(get_machine_principal),
):
    try:
        safe_purpose, redaction_counts = sanitize_text(body.purpose.strip())
    except DataProtectionBlocked as exc:
        raise HTTPException(422, "Session purpose blocked by data-protection policy") from exc
    session = create_agent_session(db, principal, purpose=safe_purpose,
                                   data_class=body.data_class, ttl_seconds=body.ttl_seconds)
    record_event(
        db, session.org_id, None, "agent_session.created",
        "agent_session", session.id, session.workspace_id,
        {"machine_identity_id": session.machine_identity_id,
         "data_class": session.data_class,
         "purpose_redaction_counts": redaction_counts},
    )
    db.commit()
    return {"id": session.id, "org_id": session.org_id, "workspace_id": session.workspace_id,
            "machine_identity_id": session.machine_identity_id, "purpose": session.purpose,
            "data_class": session.data_class, "status": session.status, "expires_at": session.expires_at}
