# High-impact actions must have an OS-owned approval record before execution.
# Actual execution endpoints must call require_approved_action in the same
# transaction as the protected state change.
MANDATORY_APPROVAL_ACTIONS = {
    "contract.execute",
    "pricing.change",
    "payment.issue",
    "external_communication.sensitive",
    "production.release",
    "resource.delete",
    "client_data.delete",
    "security.permission.change",
}

def is_approval_required(action_type: str) -> bool:
    return action_type in MANDATORY_APPROVAL_ACTIONS
