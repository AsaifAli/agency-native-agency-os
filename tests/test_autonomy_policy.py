from app.autonomy_policy import ActionDisposition, action_disposition


def test_internal_routine_work_is_classified_autonomous():
    assert action_disposition("crm.lead.update") == ActionDisposition.AUTONOMOUS
    assert action_disposition("transcript.process") == ActionDisposition.AUTONOMOUS


def test_high_impact_actions_require_founder_approval():
    assert action_disposition("production.release") == ActionDisposition.FOUNDER_APPROVAL
    assert action_disposition("pricing.change") == ActionDisposition.FOUNDER_APPROVAL


def test_unknown_or_unregistered_actions_default_to_manual_review():
    assert action_disposition("telephony.outbound.dial") == ActionDisposition.MANUAL_REVIEW
    assert action_disposition("some.new.action") == ActionDisposition.MANUAL_REVIEW
