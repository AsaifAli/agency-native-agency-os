
from app.integrations.mock_runtime import MockRuntime
from app.integrations.runtime import ExecutionRequest
from app.models import DataClass


def test_mock_runtime_returns_deterministic_success():
    request = ExecutionRequest(
        org_id="org-test",
        workspace_id="workspace-test",
        task_id="task-test",
        agent_id="agent-test",
        data_class=DataClass.synthetic,
    )

    result = MockRuntime().start(request)

    assert result.provider == "mock"
    assert result.external_run_id == "mock-task-test"
    assert result.status == "succeeded"
    assert result.detail == "Mock execution completed successfully."
