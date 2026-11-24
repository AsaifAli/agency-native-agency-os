import pytest

from app.config import settings
from app.integrations.runtime_registry import (
    enabled_runtime_names,
    is_runtime_available,
)
from app.worker.runtime_factory import (
    RuntimeNotConfiguredError,
    get_runtime,
)
from app.integrations.mock_runtime import MockRuntime


def test_mock_runtime_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "mock_runtime_enabled", False)

    assert enabled_runtime_names() == frozenset()
    assert not is_runtime_available("mock")
    with pytest.raises(RuntimeNotConfiguredError):
        get_runtime("mock")


@pytest.mark.parametrize("environment", ["development", "test"])
def test_mock_runtime_requires_explicit_enablement(monkeypatch, environment):
    monkeypatch.setattr(settings, "app_env", environment)
    monkeypatch.setattr(settings, "mock_runtime_enabled", True)

    assert is_runtime_available("mock")
    assert isinstance(get_runtime("mock"), MockRuntime)


@pytest.mark.parametrize("environment", ["production", "staging", "PRODUCTION"])
def test_mock_runtime_is_never_enabled_outside_dev_or_test(
    monkeypatch,
    environment,
):
    monkeypatch.setattr(settings, "app_env", environment)
    monkeypatch.setattr(settings, "mock_runtime_enabled", True)

    assert not is_runtime_available("mock")
    with pytest.raises(RuntimeNotConfiguredError):
        get_runtime("mock")


@pytest.mark.parametrize(
    "runtime_name",
    ["claude_managed_agents", "claude_agent_sdk", "unknown"],
)
def test_unconfigured_provider_runtimes_are_unavailable(
    monkeypatch,
    runtime_name,
):
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "mock_runtime_enabled", True)

    assert not is_runtime_available(runtime_name)
    with pytest.raises(RuntimeNotConfiguredError):
        get_runtime(runtime_name)


def test_managed_agents_requires_explicit_flag_and_complete_configuration():
    from types import SimpleNamespace

    config = SimpleNamespace(
        app_env="development",
        mock_runtime_enabled=False,
        claude_managed_agents_enabled=True,
        anthropic_api_key="test-key",
        claude_managed_agent_id="agent_test",
        claude_managed_environment_id="env_test",
    )
    assert is_runtime_available("claude_managed_agents", config)


def test_managed_agents_stays_disabled_when_any_required_setting_is_missing():
    from types import SimpleNamespace

    config = SimpleNamespace(
        app_env="development",
        mock_runtime_enabled=False,
        claude_managed_agents_enabled=True,
        anthropic_api_key="test-key",
        claude_managed_agent_id="",
        claude_managed_environment_id="env_test",
    )
    assert not is_runtime_available("claude_managed_agents", config)
