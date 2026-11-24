"""Authenticated read-only API for the curated Agent Skills catalog."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import Principal, get_principal, require_membership
from app.db import get_db
from app.skills_registry import SkillCatalogError, SkillNotFound, get_skill, list_skills

router = APIRouter(prefix="/v1/orgs/{org_id}/skills", tags=["skills"])


@router.get("")
def read_skill_catalog(
    org_id: str,
    category: str | None = Query(default=None, min_length=2, max_length=40),
    q: str | None = Query(default=None, min_length=1, max_length=120),
    db: Session = Depends(get_db),
    p: Principal = Depends(get_principal),
):
    require_membership(org_id, p, db)
    try:
        return {"skills": list_skills(category=category, query=q)}
    except SkillCatalogError as exc:
        raise HTTPException(503, "Skill catalog is not available") from exc


@router.get("/{skill_name}")
def read_skill(
    org_id: str,
    skill_name: str,
    db: Session = Depends(get_db),
    p: Principal = Depends(get_principal),
):
    require_membership(org_id, p, db)
    try:
        return get_skill(skill_name)
    except SkillNotFound as exc:
        raise HTTPException(404, "Skill not found") from exc
    except SkillCatalogError as exc:
        raise HTTPException(503, "Skill catalog is not available") from exc
