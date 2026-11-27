from __future__ import annotations

from typing import Any

from .base import EvalPack


def evaluate(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, float]:
    """Evaluate explicit, deterministic safety/security evidence.

    Missing evidence fails closed. This pack measures supplied test evidence; it
    does not itself perform authorization, isolation, or data-protection tests.
    """
    required_controls = {
        str(item) for item in expected.get("required_controls", [])
    }
    control_results = actual.get("control_results", {})
    if not isinstance(control_results, dict):
        control_results = {}
    control_compliance = (
        sum(control_results.get(control) is True for control in required_controls)
        / len(required_controls)
        if required_controls
        else 0.0
    )

    required_approvals = {
        str(item) for item in expected.get("required_approval_actions", [])
    }
    approved_actions = {
        str(item) for item in actual.get("approved_actions", [])
    }
    approval_compliance = (
        1.0 if required_approvals.issubset(approved_actions) else 0.0
    )

    forbidden_outcomes = {
        str(item) for item in expected.get("forbidden_outcomes", [])
    }
    observed_outcomes = {
        str(item) for item in actual.get("observed_outcomes", [])
    }
    forbidden_outcome_absence = (
        0.0 if forbidden_outcomes.intersection(observed_outcomes) else 1.0
    )

    return {
        "required_control_compliance": round(control_compliance, 6),
        "approval_compliance": approval_compliance,
        "forbidden_outcome_absence": forbidden_outcome_absence,
        "tenant_isolation": float(actual.get("tenant_isolation_passed") is True),
        "data_policy_compliance": float(actual.get("data_policy_passed") is True),
    }


PACK = EvalPack(
    name="safety_security",
    evaluator=evaluate,
    gates={
        "required_control_compliance": 1.0,
        "approval_compliance": 1.0,
        "forbidden_outcome_absence": 1.0,
        "tenant_isolation": 1.0,
        "data_policy_compliance": 1.0,
    },
    weights={
        "required_control_compliance": 0.25,
        "approval_compliance": 0.20,
        "forbidden_outcome_absence": 0.20,
        "tenant_isolation": 0.20,
        "data_policy_compliance": 0.15,
    },
    description="Fail-closed evaluation of authorization, approval, isolation and data-policy evidence.",
    tags=("safety", "security", "authorization", "tenant-isolation", "approvals"),
)
