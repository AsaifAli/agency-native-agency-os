
from datetime import datetime, timezone

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
