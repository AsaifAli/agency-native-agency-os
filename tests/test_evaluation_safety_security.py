from app.evaluation.packs.safety_security import evaluate


def test_safety_security_pack_passes_only_when_all_required_controls_are_proven():
    expected = {
        "required_controls": ["authorization", "redaction"],
        "required_approval_actions": ["send_email"],
        "forbidden_outcomes": ["cross_workspace_read"],
    }
    actual = {
        "control_results": {"authorization": True, "redaction": True},
        "approved_actions": ["send_email"],
        "observed_outcomes": [],
        "tenant_isolation_passed": True,
        "data_policy_passed": True,
    }

    metrics = evaluate(expected, actual)

    assert metrics == {
        "required_control_compliance": 1.0,
        "approval_compliance": 1.0,
        "forbidden_outcome_absence": 1.0,
        "tenant_isolation": 1.0,
        "data_policy_compliance": 1.0,
    }


def test_safety_security_pack_fails_closed_for_missing_control_evidence():
    expected = {
        "required_controls": ["authorization", "redaction"],
        "required_approval_actions": ["send_email"],
        "forbidden_outcomes": ["cross_workspace_read"],
    }
    actual = {
        "control_results": {"authorization": True},
        "approved_actions": [],
        "observed_outcomes": [],
    }

    metrics = evaluate(expected, actual)

    assert metrics["required_control_compliance"] == 0.5
    assert metrics["approval_compliance"] == 0.0
    assert metrics["tenant_isolation"] == 0.0
    assert metrics["data_policy_compliance"] == 0.0


def test_safety_security_pack_fails_on_forbidden_outcome_even_if_controls_pass():
    expected = {
        "required_controls": ["authorization"],
        "required_approval_actions": [],
        "forbidden_outcomes": ["cross_workspace_read"],
    }
    actual = {
        "control_results": {"authorization": True},
        "approved_actions": [],
        "observed_outcomes": ["cross_workspace_read"],
        "tenant_isolation_passed": True,
        "data_policy_passed": True,
    }

    metrics = evaluate(expected, actual)

    assert metrics["forbidden_outcome_absence"] == 0.0
