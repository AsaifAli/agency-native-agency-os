from abc import ABC, abstractmethod
from dataclasses import dataclass
from app.models import DataClass
from app.policy import assert_managed_agents_eligible

@dataclass
class ExecutionRequest:
    org_id: str
    workspace_id: str
    task_id: str
    agent_id: str
    data_class: DataClass
    client_authorized: bool = False

@dataclass
class ExecutionResult:
    provider: str
    external_run_id: str | None
    status: str
    detail: str = ""

class AgentRuntime(ABC):
    @abstractmethod
    def start(self, request: ExecutionRequest) -> ExecutionResult: ...

class ManagedAgentsRuntime(AgentRuntime):
    def start(self, request: ExecutionRequest) -> ExecutionResult:
        assert_managed_agents_eligible(request.data_class, request.client_authorized)
        # TODO: Implement against the current official API behind this adapter.
        # Never store provider state as the OS source of truth.
        return ExecutionResult("claude_managed_agents", None, "not_configured",
                               "Runtime adapter boundary is ready; provider integration is not configured.")

class AgentSdkRuntime(AgentRuntime):
    def start(self, request: ExecutionRequest) -> ExecutionResult:
        # Alternative route for workloads that cannot use Managed Agents.
        return ExecutionResult("claude_agent_sdk", None, "not_configured",
                               "Self-managed runtime adapter is not configured.")
