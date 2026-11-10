from __future__ import annotations

from integrations.evaluation_harness_source.evals.registry import get_pack, pack_catalog


def evaluate(pack_name: str, expected: dict, actual: dict) -> dict:
    pack = get_pack(pack_name)
    metrics = pack.evaluator(expected, actual)
    gate_results = {
        metric: {
            "threshold": threshold,
            "actual": float(metrics.get(metric, 0.0)),
            "passed": float(metrics.get(metric, 0.0)) >= float(threshold),
        }
        for metric, threshold in pack.gates.items()
    }
    weight_total = sum(float(v) for v in pack.weights.values()) or 1.0
    score = round(
        sum(float(metrics.get(k, 0.0)) * float(w) for k, w in pack.weights.items())
        / weight_total,
        6,
    )
    return {
        "pack_name": pack.name,
        "score": score,
        "passed": all(item["passed"] for item in gate_results.values()),
        "metrics": metrics,
        "gate_results": gate_results,
    }


def catalog() -> list[dict]:
    return pack_catalog()
