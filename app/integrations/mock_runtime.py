
from app.integrations.runtime import (
    AgentRuntime,
    ExecutionRequest,
    ExecutionResult,
)


class MockRuntime(AgentRuntime):
    """Deterministic local runtime for worker lifecycle testing.

    This runtime performs no external calls and processes no client content.
    """

    def start(self, request: ExecutionRequest) -> ExecutionResult:
        return ExecutionResult(
            provider="mock",
            external_run_id=f"mock-{request.task_id}",
            status="succeeded",
            detail="Mock execution completed successfully.",
        )
