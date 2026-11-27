"""Founder-only operational visibility for the transactional outbox.

This surface intentionally returns aggregate counts and timestamps only. Event
payloads, idempotency keys, provider errors and workspace identifiers are not
exposed in the response.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import (
    Principal,
    get_principal,
    require_founder_authority,
    require_membership,
    require_workspace_access,
)
from app.db import get_db
from app.outbox_service import summarize_outbox

router = APIRouter(tags=["founder-operations"])


@router.get("/v1/orgs/{org_id}/workspaces/{workspace_id}/outbox/summary")
def get_outbox_summary(
    org_id: str,
    workspace_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    require_membership(org_id, principal, db)
    require_workspace_access(org_id, workspace_id, principal, db)
    require_founder_authority(db, org_id, principal.user.id)
    return summarize_outbox(db, org_id=org_id, workspace_id=workspace_id)
