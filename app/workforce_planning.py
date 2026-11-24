"""Pure validation helpers for Claude-generated Chief of Staff plan drafts."""
from __future__ import annotations

import json

from pydantic import ValidationError

from app.workforce_schemas import SuggestedPlan


class PlanDraftOutputError(ValueError):
    """The model output is not a valid, bounded Agency OS plan proposal."""


def validate_plan_draft_output(detail: str) -> dict:
    """Parse strict JSON and validate the complete proposal before persistence."""
    if not isinstance(detail, str) or not detail.strip():
        raise PlanDraftOutputError("empty_output")
    if len(detail.encode("utf-8")) > 20_000:
        raise PlanDraftOutputError("output_too_large")
    try:
        payload = json.loads(detail)
    except (TypeError, ValueError) as exc:
        raise PlanDraftOutputError("invalid_json") from exc
    try:
        plan = SuggestedPlan.model_validate(payload)
    except ValidationError as exc:
        raise PlanDraftOutputError("schema_invalid") from exc
    return plan.model_dump(mode="json")
