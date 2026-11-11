
from app.integrations.mock_runtime import MockRuntime
from app.integrations.runtime import AgentRuntime


class RuntimeNotConfiguredError(Exception):
    """Raised when a requested runtime is unavailable."""


def get_runtime(runtime_name: str) -> AgentRuntime:
    """Return an explicitly supported local runtime."""

    if runtime_name == "mock":
        return MockRuntime()

    raise RuntimeNotConfiguredError(
        f"Runtime '{runtime_name}' is not enabled in this worker."
    )
