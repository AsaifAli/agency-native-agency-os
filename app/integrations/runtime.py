from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable

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
    agent_name: str = ""
    agent_department: str = ""
    agent_instructions: str = ""
    task_title: str = ""
    task_description: str = ""
    external_run_id: str | None = None
    persist_external_run_id: Callable[[str], None] | None = None


@dataclass
class ExecutionResult:
    provider: str
    external_run_id: str | None
    status: str
    detail: str = ""


class RuntimeExecutionError(Exception):
    """The provider completed with an unsuccessful or unusable result."""


class RuntimeTransientError(RuntimeExecutionError):
    """A retryable provider/network failure."""


class RuntimeManualReviewRequired(RuntimeExecutionError):
    """The provider paused for a tool approval or other human decision."""


class AgentRuntime(ABC):
    @abstractmethod
    def start(self, request: ExecutionRequest) -> ExecutionResult: ...


class AgentSdkRuntime(AgentRuntime):
    def start(self, request: ExecutionRequest) -> ExecutionResult:
        # Alternative route for workloads that cannot use Managed Agents.
        return ExecutionResult(
            "claude_agent_sdk",
            None,
            "not_configured",
            "Self-managed runtime adapter is not configured.",
        )
