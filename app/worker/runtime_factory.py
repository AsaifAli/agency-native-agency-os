from app.integrations.mock_runtime import MockRuntime
from app.integrations.runtime import AgentRuntime
from app.integrations.runtime_registry import is_runtime_available


class RuntimeNotConfiguredError(Exception):
    """Raised when a requested runtime is unavailable."""


def get_runtime(runtime_name: str) -> AgentRuntime:
    """Return a runtime explicitly enabled for this environment."""

    if not is_runtime_available(runtime_name):
        raise RuntimeNotConfiguredError(
            f"Runtime '{runtime_name}' is not enabled in this environment."
        )

    if runtime_name == "mock":
        return MockRuntime()

    # The registry and factory intentionally fail closed if they drift.
    raise RuntimeNotConfiguredError(
        f"Runtime '{runtime_name}' has no worker adapter."
    )
