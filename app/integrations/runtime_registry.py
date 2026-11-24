"""Single source of truth for runtimes enabled in this environment.

Provider adapters remain unavailable until they are fully configured. The mock
runtime is strictly a local synthetic-data test capability.
"""

from app.config import settings


def enabled_runtime_names(config=settings) -> frozenset[str]:
    environment = str(config.app_env).strip().lower()
    if (
        environment in {"development", "test"}
        and config.mock_runtime_enabled is True
    ):
        return frozenset({"mock"})
    return frozenset()


def is_runtime_available(runtime_name: str, config=settings) -> bool:
    return (
        isinstance(runtime_name, str)
        and runtime_name in enabled_runtime_names(config)
    )
