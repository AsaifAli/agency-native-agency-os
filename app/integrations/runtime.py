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
    execution_id: str | None = None
    client_authorized: bool = False
    agent_name: str = ""
    agent_department: str = ""
    agent_instructions: str = ""
    task_title: str = ""
    task_description: str = ""
    external_run_id: str | None = None
    attempt_number: int = 1
    persist_external_run_id: Callable[[str], None] | None = None
    persist_resume_event: Callable[[str, str], None] | None = None
    persist_control_event: Callable[[str, str], None] | None = None
    execute_custom_tool: Callable[[str, dict, str], dict] | None = None
    prepare_mcp_session: Callable[[], dict] | None = None
    get_mcp_provider_credential: Callable[[], dict | None] | None = None
    persist_mcp_provider_credential: Callable[[str, str, str], None] | None = None
    revoke_mcp_session_credential: Callable[[str, str], None] | None = None
    mark_mcp_provider_credential_archived: Callable[[str, str], None] | None = None
    control_check: Callable[[], str | None] | None = None
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


class RuntimeCancelled(RuntimeExecutionError):
    """The provider acknowledged a durable OS cancellation request."""


class RuntimePaused(RuntimeExecutionError):
    """The provider acknowledged a durable OS pause request and is idle."""


class RuntimeToolRejected(Exception):
    """An OS policy or authorization gate explicitly rejected a tool call."""


class AgentRuntime(ABC):
    @abstractmethod
    def start(self, request: ExecutionRequest) -> ExecutionResult: ...


class AgentSdkRuntime(AgentRuntime):
    def start(self, request: ExecutionRequest) -> ExecutionResult:
        return ExecutionResult(
            "claude_agent_sdk", None, "not_configured",
            "Self-managed runtime adapter is not configured.",
        )
