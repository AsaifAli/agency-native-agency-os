from types import SimpleNamespace

import pytest

from app.tool_gateway import (
    DEFAULT_MAX_TOOL_CALLS_PER_SESSION,
    _effective_session_tool_policy,
)


def test_session_tool_policy_uses_machine_scopes_and_default_call_ceiling():
    identity = SimpleNamespace(scopes=["tools:invoke", "tool:health.check", "tool:lead.research"])

    allowed, limit = _effective_session_tool_policy(
        identity,
        allowed_tool_keys=None,
        max_calls_per_session=None,
    )

    assert allowed == frozenset({"health.check", "lead.research"})
    assert limit == DEFAULT_MAX_TOOL_CALLS_PER_SESSION == 100


def test_adapter_policy_can_only_narrow_machine_tool_scopes_and_call_limit():
    identity = SimpleNamespace(scopes=["tools:invoke", "tool:health.check", "tool:lead.research"])

    allowed, limit = _effective_session_tool_policy(
        identity,
        allowed_tool_keys={"health.check"},
        max_calls_per_session=7,
    )

    assert allowed == frozenset({"health.check"})
    assert limit == 7


def test_adapter_cannot_expand_default_session_call_ceiling():
    identity = SimpleNamespace(scopes=["tools:invoke", "tool:health.check"])

    _, limit = _effective_session_tool_policy(
        identity,
        allowed_tool_keys=None,
        max_calls_per_session=10000,
    )

    assert limit == 100


def test_session_tool_policy_fails_closed_without_invoke_scope():
    identity = SimpleNamespace(scopes=["tool:health.check"])

    allowed, limit = _effective_session_tool_policy(
        identity,
        allowed_tool_keys=None,
        max_calls_per_session=None,
    )

    assert allowed == frozenset()
    assert limit == 100


@pytest.mark.parametrize("limit", [True, 0, -1, "10"])
def test_session_tool_policy_rejects_invalid_call_limits(limit):
    identity = SimpleNamespace(scopes=["tools:invoke", "tool:health.check"])

    with pytest.raises(ValueError):
        _effective_session_tool_policy(
            identity,
            allowed_tool_keys=None,
            max_calls_per_session=limit,
        )


def test_session_tool_policy_rejects_malformed_adapter_allowlist():
    identity = SimpleNamespace(scopes=["tools:invoke", "tool:health.check"])

    with pytest.raises(ValueError):
        _effective_session_tool_policy(
            identity,
            allowed_tool_keys={"../admin"},
            max_calls_per_session=None,
        )
