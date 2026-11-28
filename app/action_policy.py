
from datetime import datetime, timezone
import uuid

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.audit import record_event
from app.models import Approval, ApprovalStatus, Membership, User
from app.auth import has_founder_authority


MANDATORY_APPROVAL_ACTIONS = {
    "contract.execute",
    "delivery.activate",
    "invoice.issue",
    "pricing.change",
    "payment.issue",
    "external_communication.sensitive",
    "production.release",
    "resource.delete",
    "client_data.delete",
    "security.permission.change",
    "scope.change.accept",
}


def workspace_access_resource_id(workspace_id: str, user_id: str, operation: str) -> str:
    """Stable, opaque resource key bound to one grant or revoke operation."""
    if operation not in {"grant", "revoke"}:
        raise ValueError("Workspace access operation must be grant or revoke")
    return str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"agency-os:workspace-access:v1:{operation}:{workspace_id}:{user_id}",
    ))


def machine_identity_provision_resource_id(
    workspace_id: str, subject_type: str, subject_id: str, name: str,
) -> str:
    """Stable resource key for a specific machine identity provisioning intent."""
    return str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"agency-os:machine-identity:v1:create:{workspace_id}:{subject_type}:{subject_id}:{name.strip()}",
    ))


def machine_identity_revocation_resource_id(identity_id: str) -> str:
    """Stable resource key for revoking one machine identity."""
    return str(uuid.uuid5(
        uuid.NAMESPACE_URL, f"agency-os:machine-identity:v1:revoke:{identity_id}",
    ))


def workforce_capability_resource_id(
    workspace_id: str, member_id: str, capability_key: str, operation: str,
) -> str:
    """Stable resource key for one workforce capability configuration or enablement."""
    if operation not in {"configure", "enable"}:
        raise ValueError("Workforce capability operation must be configure or enable")
    return str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"agency-os:workforce-capability:v1:{operation}:{workspace_id}:{member_id}:{capability_key}",
    ))


def workforce_member_activation_resource_id(workspace_id: str, member_id: str) -> str:
    """Stable resource key for activating one workspace workforce member."""
    return str(uuid.uuid5(
        uuid.NAMESPACE_URL, f"agency-os:workforce-member:v1:activate:{workspace_id}:{member_id}",
    ))



def agent_version_resource_id(
    workspace_id: str, agent_id: str, version_id: str, operation: str,
) -> str:
    """Stable approval resource for activating or rolling back one Agent version."""
    if operation not in {"activate", "rollback"}:
        raise ValueError("Agent version operation must be activate or rollback")
    return str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"agency-os:agent-version:v1:{operation}:{workspace_id}:{agent_id}:{version_id}",
    ))



def is_approval_required(action_type: str) -> bool:
    return action_type in MANDATORY_APPROVAL_ACTIONS


def require_approved_action(
    db: Session,
    *,
    approval_id: str,
    org_id: str,
    workspace_id: str,
    action_type: str,
    resource_id: str,
    actor_user_id: str,
    expected_request_payload: dict | None = None,
) -> Approval:
    """Validate and consume an approval within the caller's transaction."""

    if not is_approval_required(action_type):
        raise ValueError(
            f"Action does not require mandatory approval: {action_type}"
        )

    if not actor_user_id:
        raise HTTPException(
            status_code=403,
            detail="An authenticated actor is required",
        )

    actor_is_active_member = (
        db.query(User.id)
        .join(Membership, Membership.user_id == User.id)
        .filter(
            User.id == actor_user_id,
            User.active.is_(True),
            Membership.org_id == org_id,
        )
        .first()
        is not None
    )
    if not actor_is_active_member:
        raise HTTPException(
            status_code=403,
            detail="The action actor is not an active member of this organization",
        )

    approval = (
        db.query(Approval)
        .filter(
            Approval.id == approval_id,
            Approval.org_id == org_id,
        )
        .with_for_update()
        .first()
    )

    if approval is None:
        raise HTTPException(
            status_code=403,
            detail="Approval does not authorize this action",
        )

    if (
        approval.workspace_id != workspace_id
        or approval.action_type != action_type
        or approval.resource_id != resource_id
    ):
        raise HTTPException(
            status_code=403,
            detail="Approval does not authorize this action",
        )

    if expected_request_payload is not None and approval.request_payload != expected_request_payload:
        raise HTTPException(403, detail="Approval payload does not match the requested action")

    if approval.status != ApprovalStatus.approved:
        raise HTTPException(
            status_code=409,
            detail="Approval has not been approved",
        )

    if approval.decided_by is None or not has_founder_authority(
        db, org_id, approval.decided_by
    ):
        raise HTTPException(
            status_code=403,
            detail="Approval was not decided by an authorized founder",
        )

    if approval.consumed_at is not None or approval.consumed_by is not None:
        raise HTTPException(
            status_code=409,
            detail="Approval has already been consumed",
        )

    consumed_at = datetime.now(timezone.utc)

    result = db.execute(
        update(Approval)
        .where(
            Approval.id == approval_id,
            Approval.org_id == org_id,
            Approval.workspace_id == workspace_id,
            Approval.action_type == action_type,
            Approval.resource_id == resource_id,
            Approval.status == ApprovalStatus.approved,
            Approval.consumed_at.is_(None),
            Approval.consumed_by.is_(None),
        )
        .values(
            consumed_at=consumed_at,
            consumed_by=actor_user_id,
        )
        .execution_options(synchronize_session=False)
    )

    if result.rowcount != 1:
        raise HTTPException(
            status_code=409,
            detail="Approval has already been consumed or is no longer valid",
        )

    approval.consumed_at = consumed_at
    approval.consumed_by = actor_user_id

    record_event(
        db=db,
        org_id=org_id,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        event_type="approval.consumed",
        resource_type="approval",
        resource_id=approval.id,
        payload={
            "action_type": action_type,
            "protected_resource_id": resource_id,
        },
    )

    db.flush()

    return approval
