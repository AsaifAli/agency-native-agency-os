from app.evaluation.packs.regression import evaluate


def test_regression_pack_passes_when_every_required_check_is_true():
    metrics = evaluate(
        {"required_checks": ["api_contract", "migration_compatibility"]},
        {"check_results": {"api_contract": True, "migration_compatibility": True}},
    )
    assert metrics == {"required_check_pass_rate": 1.0}


def test_regression_pack_fails_closed_for_missing_or_failed_checks():
    metrics = evaluate(
        {"required_checks": ["api_contract", "migration_compatibility"]},
        {"check_results": {"api_contract": True, "migration_compatibility": False}},
    )
    assert metrics == {"required_check_pass_rate": 0.5}


def test_regression_pack_does_not_allow_empty_required_check_set_to_pass():
    metrics = evaluate({"required_checks": []}, {"check_results": {}})
    assert metrics == {"required_check_pass_rate": 0.0}
