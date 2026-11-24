"""Single source of truth for runtimes enabled in this environment.

The mock runtime is limited to explicitly enabled development/test use.
Managed Agents requires an explicit feature flag plus complete provider
configuration; it is never enabled merely because an API key exists.
"""
from app.config import settings


def enabled_runtime_names(config=settings) -> frozenset[str]:
    enabled: set[str] = set()
    environment = str(config.app_env).strip().lower()

    if (
        environment in {"development", "test"}
        and config.mock_runtime_enabled is True
    ):
        enabled.add("mock")

    if (
        config.claude_managed_agents_enabled is True
        and bool(config.anthropic_api_key)
        and bool(config.claude_managed_agent_id)
        and bool(config.claude_managed_environment_id)
    ):
        enabled.add("claude_managed_agents")

    return frozenset(enabled)


def is_runtime_available(runtime_name: str, config=settings) -> bool:
    return (
        isinstance(runtime_name, str)
        and runtime_name in enabled_runtime_names(config)
    )
