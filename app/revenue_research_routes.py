"""Founder review and promotion of agent-generated public lead research drafts."""
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import Principal, get_principal, require_founder_authority
from app.audit import record_event
from app.data_protection import DataProtectionBlocked, sanitize_text
from app.db import get_db
from app.domain_models import Lead, LeadResearchDraft, LeadResearchRecord
from app.models import Workspace

router = APIRouter(tags=["revenue-research-review"])


class LeadResearchReviewRequest(BaseModel):
    decision: Literal["approve", "reject"]
    review_note: str = Field(default="", max_length=2000)


@router.get("/v1/orgs/{org_id}/workspaces/{workspace_id}/lead-research-drafts")
def list_lead_research_drafts(
    org_id: str,
    workspace_id: str,
    status: Literal["pending_review", "approved", "rejected", "promoted"] = "pending_review",
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    require_founder_authority(db, org_id, principal.user.id)
    require_workspace_access_from_context(org_id, workspace_id, db)
    rows = (
        db.query(LeadResearchDraft)
        .filter_by(org_id=org_id, workspace_id=workspace_id, status=status)
        .order_by(LeadResearchDraft.created_at.desc(), LeadResearchDraft.id.asc())
        .limit(limit)
        .all()
    )
    return {
        "items": [
            {
                "id": row.id,
                "company_name": row.company_name,
                "summary": row.summary,
                "source_references": row.source_references,
                "fit_score": row.fit_score,
                "confidence_score": row.confidence_score,
                "buying_signals": row.buying_signals,
                "risks": row.risks,
                "status": row.status,
                "machine_identity_id": row.machine_identity_id,
                "created_at": row.created_at,
                "reviewed_at": row.reviewed_at,
                "promoted_lead_id": row.promoted_lead_id,
            }
            for row in rows
        ]
    }


@router.post("/v1/orgs/{org_id}/workspaces/{workspace_id}/lead-research-drafts/{draft_id}/review")
def review_lead_research_draft(
    org_id: str,
    workspace_id: str,
    draft_id: str,
    body: LeadResearchReviewRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    require_founder_authority(db, org_id, principal.user.id)
    require_workspace_access_from_context(org_id, workspace_id, db)
    draft = db.query(LeadResearchDraft).filter_by(
        id=draft_id, org_id=org_id, workspace_id=workspace_id
    ).with_for_update().first()
    if draft is None:
        raise HTTPException(404, "Lead research draft not found")
    if draft.status != "pending_review":
        raise HTTPException(409, "Only pending research drafts can be reviewed")
    try:
        safe_note, redaction_counts = sanitize_text(body.review_note.strip())
    except DataProtectionBlocked as exc:
        raise HTTPException(422, "Review note blocked by data-protection policy") from exc
    now = datetime.now(timezone.utc)
    draft.status = "approved" if body.decision == "approve" else "rejected"
    draft.review_note = safe_note
    draft.reviewed_by_user_id = principal.user.id
    draft.reviewed_at = now
    record_event(
        db, org_id, principal.user.id,
        "lead_research_draft.approved" if body.decision == "approve" else "lead_research_draft.rejected",
        "lead_research_draft", draft.id, workspace_id,
        {"machine_identity_id": draft.machine_identity_id,
         "decision": body.decision, "review_note_redaction_counts": redaction_counts},
    )
    db.commit()
    return {"id": draft.id, "status": draft.status, "reviewed_at": draft.reviewed_at}


@router.post("/v1/orgs/{org_id}/workspaces/{workspace_id}/lead-research-drafts/{draft_id}/promote")
def promote_lead_research_draft(
    org_id: str,
    workspace_id: str,
    draft_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    require_founder_authority(db, org_id, principal.user.id)
    draft = db.query(LeadResearchDraft).filter_by(
        id=draft_id, org_id=org_id, workspace_id=workspace_id
    ).with_for_update().first()
    if draft is None:
        raise HTTPException(404, "Lead research draft not found")
    if draft.status == "promoted" and draft.promoted_lead_id:
        return {"draft_id": draft.id, "lead_id": draft.promoted_lead_id, "status": "promoted", "replayed": True}
    if draft.status != "approved":
        raise HTTPException(409, "Research draft must be approved before CRM promotion")

    lead = Lead(
        org_id=org_id,
        workspace_id=workspace_id,
        company_name=draft.company_name,
        source="agent_research",
        external_key=draft.id,
        stage="new",
        score=draft.fit_score,
        qualification_notes=draft.summary,
        created_by=principal.user.id,
    )
    db.add(lead)
    db.flush()
    research = LeadResearchRecord(
        org_id=org_id,
        workspace_id=workspace_id,
        lead_id=lead.id,
        summary=draft.summary,
        fit_score=draft.fit_score,
        confidence_score=draft.confidence_score,
        buying_signals=draft.buying_signals,
        risks=draft.risks,
        source_references=draft.source_references,
        created_by=principal.user.id,
    )
    db.add(research)
    db.flush()
    draft.status = "promoted"
    draft.promoted_lead_id = lead.id
    record_event(
        db, org_id, principal.user.id, "lead_research_draft.promoted",
        "lead", lead.id, workspace_id,
        {"draft_id": draft.id, "machine_identity_id": draft.machine_identity_id,
         "research_record_id": research.id},
    )
    db.commit()
    return {"draft_id": draft.id, "lead_id": lead.id, "status": "promoted", "replayed": False}
