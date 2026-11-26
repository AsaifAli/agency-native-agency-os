from __future__ import annotations

from typing import Any

from .base import EvalPack


def evaluate(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, float]:
    """Score a required regression suite; missing checks fail closed."""
    required_checks = {str(item) for item in expected.get("required_checks", [])}
    check_results = actual.get("check_results", {})
    if not isinstance(check_results, dict):
        check_results = {}
    pass_rate = (
        sum(check_results.get(check) is True for check in required_checks)
        / len(required_checks)
        if required_checks
        else 0.0
    )
    return {"required_check_pass_rate": round(pass_rate, 6)}


PACK = EvalPack(
    name="regression",
    evaluator=evaluate,
    gates={"required_check_pass_rate": 1.0},
    weights={"required_check_pass_rate": 1.0},
    description="Required regression checks for API contracts, migrations and workflow behavior.",
    tags=("regression", "release", "contracts", "migrations"),
)
