"""Central action classification for founder-in-the-loop operation.

This registry is a policy vocabulary, not a substitute for endpoint-level
authorization. Every side-effect endpoint must enforce its classification,
workspace permissions, consent/data rules, budgets and audit requirements.
Unknown actions default to manual review.
"""
from enum import Enum

from app.action_policy import MANDATORY_APPROVAL_ACTIONS


class ActionDisposition(str, Enum):
    AUTONOMOUS = "autonomous"
    FOUNDER_APPROVAL = "founder_approval"
    MANUAL_REVIEW = "manual_review"


AUTONOMOUS_ACTIONS = frozenset({
    "crm.lead.create",
    "crm.lead.update",
    "crm.contact.create",
    "crm.activity.record",
    "research.execute",
    "qualification.execute",
    "task.create",
    "task.update",
    "task.execute",
    "task.delegate",
    "transcript.process",
    "report.generate",
    "plan.generate",
    "notification.internal",
})


def action_disposition(action_type: str) -> ActionDisposition:
    """Return the default governance class; unknown actions fail closed."""
    if action_type in MANDATORY_APPROVAL_ACTIONS:
        return ActionDisposition.FOUNDER_APPROVAL
    if action_type in AUTONOMOUS_ACTIONS:
        return ActionDisposition.AUTONOMOUS
    return ActionDisposition.MANUAL_REVIEW
