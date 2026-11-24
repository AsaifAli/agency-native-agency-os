from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable

from app.models import DataClass


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
    request_metadata: dict = field(default_factory=dict)


@dataclass
class ExecutionResult:
    provider: str
    external_run_id: str | None
    status: str
    detail: str = ""


class RuntimeExecutionError(Exception):
    """The provider completed with an unsuccessful or unusable result."""


class RuntimeNotConfiguredError(RuntimeExecutionError):
    """The requested runtime or provider configuration is unavailable."""


class RuntimeTransientError(RuntimeExecutionError):
    """A retryable provider/network failure."""


class RuntimeManualReviewRequired(RuntimeExecutionError):
    """The provider paused for a tool approval or other human decision."""


class AgentRuntime(ABC):
    @abstractmethod
    def start(self, request: ExecutionRequest) -> ExecutionResult: ...


class AgentSdkRuntime(AgentRuntime):
    def start(self, request: ExecutionRequest) -> ExecutionResult:
        return ExecutionResult(
            "claude_agent_sdk", None, "not_configured",
            "Self-managed runtime adapter is not configured.",
        )
