import json
from types import SimpleNamespace

import httpx
import pytest

from app.integrations.managed_agents import ManagedAgentsRuntime
from app.integrations.runtime import (
    ExecutionRequest,
    RuntimeCancelled,
    RuntimeExecutionError,
    RuntimeManualReviewRequired,
    RuntimeNotConfiguredError,
    RuntimePaused,
    RuntimeTransientError,
)
from app.models import DataClass


def config(**overrides):
    values = {
        "claude_managed_agents_enabled": True,
        "anthropic_api_key": "test-key",
        "anthropic_api_base_url": "https://api.anthropic.com",
        "anthropic_api_version": "2026-10-21",
        "anthropic_managed_agents_beta": "managed-agents-2026-04-01",
        "claude_managed_agent_id": "agent_test",
        "claude_managed_environment_id": "env_test",
        "claude_managed_session_budget_cents": 250,
        "claude_managed_timeout_seconds": 60,
        "claude_managed_poll_interval_seconds": 0.2,
        "anthropic_request_timeout_seconds": 5,
        "claude_managed_mcp_enabled": False,
        "claude_managed_mcp_public_base_url": "",
        "claude_managed_mcp_vault_id": "",
        "claude_managed_mcp_enabled_tool_keys": "",
        "claude_managed_mcp_requests_per_minute": 120,
        "claude_managed_mcp_max_concurrent_requests": 8,
        "claude_managed_mcp_max_request_body_bytes": 1048576,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def request(**overrides):
    values = {
        "org_id": "org-test", "workspace_id": "ws-test",
        "task_id": "task-test", "agent_id": "agent-local", "execution_id": "exec-test",
        "data_class": DataClass.synthetic, "client_authorized": False,
        "agent_name": "Research Analyst", "agent_department": "Business Development",
        "agent_instructions": "Research carefully.",
        "task_title": "Research target market",
        "task_description": "Prepare a synthetic test report.",
        "external_run_id": None,
        "persist_external_run_id": lambda _session_id: None,
    }
    values.update(overrides)
    return ExecutionRequest(**values)


def test_managed_agents_uses_precreated_agent_and_persists_session_id():
    seen, persisted = [], []

    def handler(req):
        seen.append(req)
        if req.method == "GET" and req.url.path == "/v1/agents/agent_test":
            return httpx.Response(200, json={"id": "agent_test", "archived_at": None,
                "tools": [], "mcp_servers": [], "skills": [], "multiagent": None})
        if req.method == "POST" and req.url.path == "/v1/sessions":
            body = json.loads(req.content)
            assert body["agent"] == "agent_test"
            assert isinstance(body["agent"], str)
            assert "tools" not in body and "mcp_servers" not in body and "skills" not in body
            assert body["budget"]["max_list_cost"] == {"amount": "250", "currency": "USD"}
            assert body["metadata"]["agency_os_execution_id"] == "exec-test"
            message = body["initial_events"][0]["content"][0]["text"]
            assert "Research target market" in message
            assert "Research Analyst" in message
            assert "Research carefully." in message
            assert req.headers["authorization"] == "Bearer test-key"
            assert req.headers["anthropic-beta"] == "managed-agents-2026-04-01"
            return httpx.Response(200, json={"id": "sesn_test", "status": "running"})
        if req.method == "GET" and req.url.path == "/v1/sessions/sesn_test":
            return httpx.Response(200, json={"id": "sesn_test", "status": "idle"})
        if req.method == "GET" and req.url.path == "/v1/sessions/sesn_test/events":
            return httpx.Response(200, json={"data": [
                {"type": "agent.message", "content": [{"type": "text", "text": "Research completed."}]},
                {"type": "session.status_idle", "stop_reason": {"type": "end_turn"}},
            ]})
        return httpx.Response(404)

    runtime = ManagedAgentsRuntime(
        config(),
        client_factory=lambda: httpx.Client(
            base_url="https://api.anthropic.com",
            headers={
                "Authorization": "Bearer test-key",
                "anthropic-version": "2026-10-21",
                "anthropic-beta": "managed-agents-2026-04-01",
                "Content-Type": "application/json",
            },
            transport=httpx.MockTransport(handler),
        ),
        sleep=lambda _seconds: None,
    )
    result = runtime.start(request(persist_external_run_id=persisted.append))
    assert result.provider == "claude_managed_agents"
    assert result.external_run_id == "sesn_test"
    assert result.status == "succeeded"
    assert result.detail == "Research completed."
    assert persisted == ["sesn_test"]
    assert len(seen) == 4


def test_managed_agents_resumes_persisted_session_without_creating_another():
    calls = []

    def handler(req):
        calls.append((req.method, req.url.path))
        if req.method == "GET" and req.url.path == "/v1/agents/agent_test":
            return httpx.Response(200, json={"id": "agent_test", "archived_at": None, "tools": [], "mcp_servers": [], "skills": [], "multiagent": {"type": "disabled"}})
        if req.method == "GET" and req.url.path == "/v1/sessions/sesn_existing":
            return httpx.Response(200, json={"id": "sesn_existing", "status": "idle"})
        if req.method == "GET" and req.url.path == "/v1/sessions/sesn_existing/events":
            return httpx.Response(200, json={"data": [
                {"type": "agent.message", "content": [{"type": "text", "text": "Recovered result."}]},
                {"type": "session.status_idle", "stop_reason": {"type": "end_turn"}},
            ]})
        return httpx.Response(404)

    runtime = ManagedAgentsRuntime(
        config(),
        client_factory=lambda: httpx.Client(base_url="https://api.anthropic.com", transport=httpx.MockTransport(handler)),
        sleep=lambda _seconds: None,
    )
    result = runtime.start(request(external_run_id="sesn_existing"))
    assert result.external_run_id == "sesn_existing"
    assert result.detail == "Recovered result."
    assert calls == [
        ("GET", "/v1/agents/agent_test"),
        ("GET", "/v1/sessions/sesn_existing"),
        ("GET", "/v1/sessions/sesn_existing/events"),
    ]


def test_managed_agents_never_auto_confirms_tool_actions():
    def handler(req):
        if req.method == "GET" and req.url.path == "/v1/agents/agent_test":
            return httpx.Response(200, json={"id": "agent_test", "archived_at": None,
                "tools": [], "mcp_servers": [], "skills": [], "multiagent": None})
        if req.method == "POST":
            assert json.loads(req.content)["agent"] == "agent_test"
            return httpx.Response(200, json={"id": "sesn_review"})
        if req.url.path == "/v1/sessions/sesn_review":
            return httpx.Response(200, json={"id": "sesn_review", "status": "idle"})
        return httpx.Response(200, json={"data": [
            {"type": "session.status_idle", "stop_reason": {"type": "requires_action", "event_ids": ["evt_tool_1"]}}
        ]})

    runtime = ManagedAgentsRuntime(
        config(),
        client_factory=lambda: httpx.Client(base_url="https://api.anthropic.com", transport=httpx.MockTransport(handler)),
        sleep=lambda _seconds: None,
    )
    with pytest.raises(RuntimeManualReviewRequired):
        runtime.start(request())


def test_managed_agents_retries_transient_provider_errors():
    runtime = ManagedAgentsRuntime(
        config(),
        client_factory=lambda: httpx.Client(
            base_url="https://api.anthropic.com",
            transport=httpx.MockTransport(lambda _req: httpx.Response(503, json={"error": "unavailable"})),
        ),
        sleep=lambda _seconds: None,
    )
    with pytest.raises(RuntimeTransientError):
        runtime.start(request())


def test_managed_agents_rejects_confidential_data_before_network_call():
    called = []
    runtime = ManagedAgentsRuntime(
        config(),
        client_factory=lambda: httpx.Client(
            base_url="https://api.anthropic.com",
            transport=httpx.MockTransport(lambda req: called.append(req) or httpx.Response(200)),
        ),
    )
    with pytest.raises(Exception):
        runtime.start(request(data_class=DataClass.confidential))
    assert called == []


def test_managed_agents_rejects_provider_agent_with_unreviewed_tools():
    calls = []
    def handler(req):
        calls.append((req.method, req.url.path))
        if req.method == "GET" and req.url.path == "/v1/agents/agent_test":
            return httpx.Response(200, json={
                "id": "agent_test", "archived_at": None,
                "tools": [{"type": "agent_toolset_20260401", "configs": []}],
                "mcp_servers": [], "skills": [], "multiagent": None,
            })
        return httpx.Response(200, json={"id": "unexpected"})
    runtime = ManagedAgentsRuntime(
        config(),
        client_factory=lambda: httpx.Client(
            base_url="https://api.anthropic.com",
            transport=httpx.MockTransport(handler),
        ),
    )
    with pytest.raises(RuntimeNotConfiguredError):
        runtime.start(request())
    assert calls == [("GET", "/v1/agents/agent_test")]


def test_managed_agents_waits_for_workflow_run_end_before_accepting_idle():
    event_calls = []
    first = [
        {"type": "workflow_run.created", "workflow_run_id": "wrun_1", "name": "Research"},
        {"type": "session.status_idle", "stop_reason": {"type": "end_turn"}},
    ]
    second = [
        {"type": "workflow_run.created", "workflow_run_id": "wrun_1", "name": "Research"},
        {"type": "workflow_run.status_ended", "workflow_run_id": "wrun_1", "result": {"type": "completed"}},
        {"type": "agent.message", "content": [{"type": "text", "text": "Workflow report."}]},
        {"type": "session.status_idle", "stop_reason": {"type": "end_turn"}},
    ]
    def handler(req):
        if req.method == "GET" and req.url.path == "/v1/agents/agent_test":
            return httpx.Response(200, json={"id": "agent_test", "archived_at": None,
                "tools": [], "mcp_servers": [], "skills": [], "multiagent": None})
        if req.method == "POST":
            return httpx.Response(200, json={"id": "sesn_workflow"})
        if req.method == "GET" and req.url.path == "/v1/sessions/sesn_workflow":
            return httpx.Response(200, json={"id": "sesn_workflow", "status": "idle"})
        if req.method == "GET" and req.url.path == "/v1/sessions/sesn_workflow/events":
            event_calls.append(1)
            return httpx.Response(200, json={"data": first if len(event_calls) == 1 else second})
        return httpx.Response(404)
    runtime = ManagedAgentsRuntime(
        config(),
        client_factory=lambda: httpx.Client(
            base_url="https://api.anthropic.com",
            transport=httpx.MockTransport(handler),
        ),
        sleep=lambda _seconds: None,
    )
    result = runtime.start(request())
    assert result.detail == "Workflow report."
    assert len(event_calls) == 2



def test_managed_agents_dispatches_registered_custom_tool_while_session_is_running():
    from app.tool_registry import managed_agent_custom_tool_definitions

    tool = next(item for item in managed_agent_custom_tool_definitions() if item["name"] == "os_system_health_read")
    state = {"answered": False, "session_polls": 0}
    posted = []
    calls = []

    def handler(req):
        if req.method == "GET" and req.url.path == "/v1/agents/agent_test":
            return httpx.Response(200, json={
                "id": "agent_test", "archived_at": None, "tools": [tool],
                "mcp_servers": [], "skills": [], "multiagent": None,
            })
        if req.method == "POST" and req.url.path == "/v1/sessions":
            return httpx.Response(200, json={"id": "sesn_custom_tool"})
        if req.method == "GET" and req.url.path == "/v1/sessions/sesn_custom_tool":
            state["session_polls"] += 1
            status = "running" if state["session_polls"] == 1 else "idle"
            return httpx.Response(200, json={"id": "sesn_custom_tool", "status": status})
        if req.method == "GET" and req.url.path == "/v1/sessions/sesn_custom_tool/events":
            if not state["answered"]:
                return httpx.Response(200, json={"data": [{
                    "type": "agent.custom_tool_use",
                    "id": "sevt_custom_1",
                    "name": "os_system_health_read",
                    "input": {},
                }]})
            return httpx.Response(200, json={"data": [
                {
                    "type": "agent.custom_tool_use", "id": "sevt_custom_1",
                    "name": "os_system_health_read", "input": {},
                },
                {
                    "type": "user.custom_tool_result", "custom_tool_use_id": "sevt_custom_1",
                    "content": [{"type": "text", "text": "{\"database\":\"ok\"}"}],
                    "is_error": False,
                },
                {"type": "agent.message", "content": [{"type": "text", "text": "Health check completed."}]},
                {"type": "session.status_idle", "stop_reason": {"type": "end_turn"}},
            ]})
        if req.method == "POST" and req.url.path == "/v1/sessions/sesn_custom_tool/events":
            posted.extend(json.loads(req.content)["events"])
            state["answered"] = True
            return httpx.Response(200, json={"data": []})
        return httpx.Response(404)

    def execute(name, payload, event_id):
        calls.append((name, payload, event_id))
        return {"database": "ok"}

    runtime = ManagedAgentsRuntime(
        config(),
        client_factory=lambda: httpx.Client(
            base_url="https://api.anthropic.com",
            transport=httpx.MockTransport(handler),
        ),
        sleep=lambda _seconds: None,
    )
    result = runtime.start(request(execute_custom_tool=execute))
    assert result.detail == "Health check completed."
    assert calls == [("os_system_health_read", {}, "sevt_custom_1")]
    assert posted[0]["type"] == "user.custom_tool_result"
    assert posted[0]["custom_tool_use_id"] == "sevt_custom_1"
    assert json.loads(posted[0]["content"][0]["text"]) == {"database": "ok"}


def test_managed_agents_rejects_provider_custom_tool_schema_drift():
    from app.tool_registry import managed_agent_custom_tool_definitions

    tool = next(item for item in managed_agent_custom_tool_definitions() if item["name"] == "os_system_health_read")
    tool = {**tool, "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}}}
    calls = []

    def handler(req):
        calls.append((req.method, req.url.path))
        if req.method == "GET" and req.url.path == "/v1/agents/agent_test":
            return httpx.Response(200, json={
                "id": "agent_test", "archived_at": None, "tools": [tool],
                "mcp_servers": [], "skills": [], "multiagent": None,
            })
        return httpx.Response(200, json={"id": "unexpected"})

    runtime = ManagedAgentsRuntime(
        config(),
        client_factory=lambda: httpx.Client(
            base_url="https://api.anthropic.com",
            transport=httpx.MockTransport(handler),
        ),
    )
    with pytest.raises(RuntimeNotConfiguredError):
        runtime.start(request(execute_custom_tool=lambda *_args: {}))
    assert calls == [("GET", "/v1/agents/agent_test")]


def test_managed_agents_revalidates_provider_tool_allowlist_when_resuming_session():
    calls = []

    def handler(req):
        calls.append((req.method, req.url.path))
        if req.method == "GET" and req.url.path == "/v1/agents/agent_test":
            return httpx.Response(200, json={
                "id": "agent_test", "archived_at": None,
                "tools": [{
                    "type": "custom", "name": "unregistered_tool",
                    "description": "untrusted", "input_schema": {"type": "object"},
                }],
                "mcp_servers": [], "skills": [], "multiagent": None,
            })
        return httpx.Response(200, json={"id": "sesn_existing", "status": "idle"})

    runtime = ManagedAgentsRuntime(
        config(),
        client_factory=lambda: httpx.Client(
            base_url="https://api.anthropic.com",
            transport=httpx.MockTransport(handler),
        ),
    )
    with pytest.raises(RuntimeNotConfiguredError):
        runtime.start(request(external_run_id="sesn_existing", execute_custom_tool=lambda *_args: {}))
    assert calls == [("GET", "/v1/agents/agent_test")]


def test_managed_agents_does_not_wait_for_unknown_blocking_event_ids():
    events = [{
        "type": "session.status_idle",
        "stop_reason": {"type": "requires_action", "event_ids": ["sevt_missing"]},
    }]
    assert ManagedAgentsRuntime._waiting_for_custom_tool_resume(
        events, {"os_system_health_read": "system.health.read"}
    ) is False


def test_managed_agents_bounds_pending_custom_tool_calls_before_dispatch():
    from app.tool_registry import managed_agent_custom_tool_definitions

    tool = next(item for item in managed_agent_custom_tool_definitions() if item["name"] == "os_system_health_read")
    events = [{
        "type": "agent.custom_tool_use",
        "id": f"sevt_many_{index}",
        "name": tool["name"],
        "input": {},
    } for index in range(11)]
    calls = []
    runtime = ManagedAgentsRuntime(config())
    with pytest.raises(RuntimeManualReviewRequired):
        runtime._process_custom_tool_events(
            None,
            "sesn_many",
            events,
            request(execute_custom_tool=lambda *args: calls.append(args) or {"ok": True}),
            {tool["name"]: "system.health.read"},
            max_calls=10,
        )
    assert calls == []


def test_managed_agents_requires_os_executor_when_custom_tools_are_enabled():
    from app.tool_registry import managed_agent_custom_tool_definitions

    tool = next(item for item in managed_agent_custom_tool_definitions() if item["name"] == "os_system_health_read")

    def handler(req):
        if req.method == "GET" and req.url.path == "/v1/agents/agent_test":
            return httpx.Response(200, json={
                "id": "agent_test", "archived_at": None, "tools": [tool],
                "mcp_servers": [], "skills": [], "multiagent": None,
            })
        return httpx.Response(200, json={"id": "unexpected"})

    runtime = ManagedAgentsRuntime(
        config(),
        client_factory=lambda: httpx.Client(
            base_url="https://api.anthropic.com",
            transport=httpx.MockTransport(handler),
        ),
    )
    with pytest.raises(RuntimeNotConfiguredError):
        runtime.start(request())


def test_managed_agents_returns_generic_error_for_explicit_os_policy_denial():
    from app.integrations.runtime import RuntimeToolRejected
    from app.tool_registry import managed_agent_custom_tool_definitions

    tool = next(item for item in managed_agent_custom_tool_definitions() if item["name"] == "os_system_health_read")
    posted = []

    def handler(req):
        if req.method == "GET" and req.url.path == "/v1/agents/agent_test":
            return httpx.Response(200, json={"id":"agent_test","archived_at":None,"tools":[tool],"mcp_servers":[],"skills":[],"multiagent":None})
        if req.method == "POST" and req.url.path == "/v1/sessions":
            return httpx.Response(200, json={"id":"sesn_policy_denied"})
        if req.method == "GET" and req.url.path == "/v1/sessions/sesn_policy_denied":
            return httpx.Response(200, json={"id":"sesn_policy_denied","status":"running" if not posted else "idle"})
        if req.method == "GET" and req.url.path == "/v1/sessions/sesn_policy_denied/events":
            if not posted:
                return httpx.Response(200, json={"data":[{"type":"agent.custom_tool_use","id":"sevt_policy_denied","name":"os_system_health_read","input":{}}]})
            return httpx.Response(200, json={"data":[
                {"type":"agent.custom_tool_use","id":"sevt_policy_denied","name":"os_system_health_read","input":{}},
                {"type":"user.custom_tool_result","custom_tool_use_id":"sevt_policy_denied"},
                {"type":"agent.message","content":[{"type":"text","text":"Tool was denied safely."}]},
                {"type":"session.status_idle","stop_reason":{"type":"end_turn"}},
            ]})
        if req.method == "POST" and req.url.path == "/v1/sessions/sesn_policy_denied/events":
            posted.extend(json.loads(req.content)["events"])
            return httpx.Response(200, json={"data":[]})
        return httpx.Response(404)

    def denied(*_args):
        raise RuntimeToolRejected("internal-secret-and-policy-details")

    runtime = ManagedAgentsRuntime(
        config(),
        client_factory=lambda: httpx.Client(base_url="https://api.anthropic.com", transport=httpx.MockTransport(handler)),
        sleep=lambda _seconds: None,
    )
    result = runtime.start(request(execute_custom_tool=denied))
    assert result.detail == "Tool was denied safely."
    assert posted[0]["is_error"] is True
    assert "internal-secret" not in posted[0]["content"][0]["text"]
    assert "OS_TOOL_CALL_REJECTED" in posted[0]["content"][0]["text"]


def test_managed_agents_propagates_unexpected_os_tool_failures_for_worker_retry():
    from app.tool_registry import managed_agent_custom_tool_definitions

    tool = next(item for item in managed_agent_custom_tool_definitions() if item["name"] == "os_system_health_read")
    posted = []

    def handler(req):
        if req.method == "GET" and req.url.path == "/v1/agents/agent_test":
            return httpx.Response(200, json={"id":"agent_test","archived_at":None,"tools":[tool],"mcp_servers":[],"skills":[],"multiagent":None})
        if req.method == "POST" and req.url.path == "/v1/sessions":
            return httpx.Response(200, json={"id":"sesn_os_failure"})
        if req.method == "GET" and req.url.path == "/v1/sessions/sesn_os_failure":
            return httpx.Response(200, json={"id":"sesn_os_failure","status":"running"})
        if req.method == "GET" and req.url.path == "/v1/sessions/sesn_os_failure/events":
            return httpx.Response(200, json={"data":[{"type":"agent.custom_tool_use","id":"sevt_os_failure","name":"os_system_health_read","input":{}}]})
        if req.method == "POST" and req.url.path == "/v1/sessions/sesn_os_failure/events":
            posted.extend(json.loads(req.content)["events"])
            return httpx.Response(200, json={"data":[]})
        return httpx.Response(404)

    def unavailable(*_args):
        raise RuntimeError("database connection unavailable")

    runtime = ManagedAgentsRuntime(
        config(),
        client_factory=lambda: httpx.Client(base_url="https://api.anthropic.com", transport=httpx.MockTransport(handler)),
        sleep=lambda _seconds: None,
    )
    with pytest.raises(RuntimeTransientError):
        runtime.start(request(execute_custom_tool=unavailable))
    assert posted == []


def test_managed_agents_interrupts_and_drains_session_on_os_cancellation():
    state = {"control_checks": 0, "interrupts": 0, "interrupt_id": "sevt_interrupt_1"}

    def control_check():
        state["control_checks"] += 1
        return "cancel" if state["control_checks"] >= 2 else None

    def handler(req):
        if req.method == "GET" and req.url.path == "/v1/agents/agent_test":
            return httpx.Response(200, json={
                "id": "agent_test", "archived_at": None,
                "tools": [], "mcp_servers": [], "skills": [], "multiagent": None,
            })
        if req.method == "POST" and req.url.path == "/v1/sessions":
            return httpx.Response(200, json={"id": "sesn_cancel"})
        if req.method == "POST" and req.url.path == "/v1/sessions/sesn_cancel/events":
            payload = json.loads(req.content)
            assert payload["events"] == [{"type": "user.interrupt"}]
            state["interrupts"] += 1
            return httpx.Response(200, json={"data": [{
                "id": state["interrupt_id"],
                "type": "user.interrupt",
                "processed_at": None,
            }]})
        if req.method == "GET" and req.url.path == "/v1/sessions/sesn_cancel":
            return httpx.Response(200, json={"id": "sesn_cancel", "status": "idle"})
        if req.method == "GET" and req.url.path == "/v1/sessions/sesn_cancel/events":
            return httpx.Response(200, json={"data": [{
                "id": state["interrupt_id"],
                "type": "user.interrupt",
                "processed_at": "2026-11-26T10:00:00Z",
            }]})
        return httpx.Response(404)

    runtime = ManagedAgentsRuntime(
        config(),
        client_factory=lambda: httpx.Client(
            base_url="https://api.anthropic.com",
            transport=httpx.MockTransport(handler),
        ),
        sleep=lambda _seconds: None,
    )
    with pytest.raises(RuntimeCancelled):
        runtime.start(request(control_check=control_check))

    assert state["interrupts"] == 1
    assert state["control_checks"] >= 2



def test_managed_agents_pause_waits_for_processed_interrupt_and_idle_session():
    calls = []
    controls = iter([None, "pause"])
    def handler(req):
        calls.append((req.method, req.url.path))
        if req.method == "GET" and req.url.path == "/v1/agents/agent_test":
            return httpx.Response(200, json={"id": "agent_test", "archived_at": None,
                "tools": [], "mcp_servers": [], "skills": [], "multiagent": None})
        if req.method == "POST" and req.url.path == "/v1/sessions/sesn_pause/events":
            return httpx.Response(200, json={"data": [{"id": "evt_interrupt"}]})
        if req.method == "GET" and req.url.path == "/v1/sessions/sesn_pause":
            return httpx.Response(200, json={"id": "sesn_pause", "status": "idle"})
        if req.method == "GET" and req.url.path == "/v1/sessions/sesn_pause/events":
            return httpx.Response(200, json={"data": [
                {"id": "evt_interrupt", "type": "user.interrupt", "processed_at": "2026-11-26T00:00:00Z"},
                {"type": "session.status_idle", "stop_reason": {"type": "interrupted"}},
            ]})
        return httpx.Response(404)
    runtime = ManagedAgentsRuntime(
        config(),
        client_factory=lambda: httpx.Client(base_url="https://api.anthropic.com",
            transport=httpx.MockTransport(handler)),
        sleep=lambda _seconds: None,
    )
    with pytest.raises(RuntimePaused):
        runtime.start(request(
            external_run_id="sesn_pause", attempt_number=2,
            control_check=lambda: next(controls),
        ))
    assert ("POST", "/v1/sessions/sesn_pause/events") in calls


def test_managed_agents_resume_reconciles_existing_marker_without_duplicate_message():
    calls, persisted = [], []
    token = "resume-token-123"
    marker = f"[agency-os-resume:{token}]"
    ticks = iter([0.0, 100.0])
    def handler(req):
        calls.append((req.method, req.url.path))
        if req.method == "GET" and req.url.path == "/v1/agents/agent_test":
            return httpx.Response(200, json={"id": "agent_test", "archived_at": None,
                "tools": [], "mcp_servers": [], "skills": None, "multiagent": None})
        if req.method == "GET" and req.url.path == "/v1/sessions/sesn_resume":
            return httpx.Response(200, json={"id": "sesn_resume", "status": "running"})
        if req.method == "GET" and req.url.path == "/v1/sessions/sesn_resume/events":
            return httpx.Response(200, json={"data": [
                {"id": "evt_resume", "type": "user.message",
                 "content": [{"type": "text", "text": f"Continue. {marker}"}]},
            ]})
        return httpx.Response(404)
    runtime = ManagedAgentsRuntime(
        config(), client_factory=lambda: httpx.Client(base_url="https://api.anthropic.com",
            transport=httpx.MockTransport(handler)),
        sleep=lambda _seconds: None, clock=lambda: next(ticks),
    )
    with pytest.raises(RuntimeTransientError):
        runtime.start(request(
            external_run_id="sesn_resume", attempt_number=2,
            request_metadata={"control_request": {"action": "resume", "resume_token": token}},
            persist_resume_event=lambda received_token, event_id: persisted.append((received_token, event_id)),
        ))
    assert persisted == [(token, "evt_resume")]
    assert ("POST", "/v1/sessions/sesn_resume/events") not in calls


def test_managed_agents_resume_sends_marker_once_and_persists_provider_event():
    calls, persisted = [], []
    token = "resume-token-456"
    def handler(req):
        calls.append((req.method, req.url.path))
        if req.method == "GET" and req.url.path == "/v1/agents/agent_test":
            return httpx.Response(200, json={"id": "agent_test", "archived_at": None,
                "tools": [], "mcp_servers": [], "skills": None, "multiagent": None})
        if req.method == "GET" and req.url.path == "/v1/sessions/sesn_resume_new":
            return httpx.Response(200, json={"id": "sesn_resume_new", "status": "running"})
        if req.method == "GET" and req.url.path == "/v1/sessions/sesn_resume_new/events":
            return httpx.Response(200, json={"data": []})
        if req.method == "POST" and req.url.path == "/v1/sessions/sesn_resume_new/events":
            body = json.loads(req.content)
            assert token in body["events"][0]["content"][0]["text"]
            return httpx.Response(200, json={"data": [{"id": "evt_resume_new"}]})
        return httpx.Response(404)
    ticks = iter([0.0, 100.0])
    runtime = ManagedAgentsRuntime(
        config(), client_factory=lambda: httpx.Client(base_url="https://api.anthropic.com",
            transport=httpx.MockTransport(handler)),
        sleep=lambda _seconds: None, clock=lambda: next(ticks),
    )
    with pytest.raises(RuntimeTransientError):
        runtime.start(request(
            external_run_id="sesn_resume_new", attempt_number=2,
            request_metadata={"control_request": {"action": "resume", "resume_token": token}},
            persist_resume_event=lambda received_token, event_id: persisted.append((received_token, event_id)),
        ))
    assert persisted == [(token, "evt_resume_new")]
    assert calls.count(("POST", "/v1/sessions/sesn_resume_new/events")) == 1



def test_managed_agents_recovers_persisted_interrupt_without_sending_another():
    calls = []
    def handler(req):
        calls.append((req.method, req.url.path))
        if req.method == "GET" and req.url.path == "/v1/agents/agent_test":
            return httpx.Response(200, json={"id": "agent_test", "archived_at": None,
                "tools": [], "mcp_servers": [], "skills": [], "multiagent": None})
        if req.method == "GET" and req.url.path == "/v1/sessions/sesn_pause_recover":
            return httpx.Response(200, json={"id": "sesn_pause_recover", "status": "idle"})
        if req.method == "GET" and req.url.path == "/v1/sessions/sesn_pause_recover/events":
            return httpx.Response(200, json={"data": [
                {"id": "evt_interrupt_saved", "type": "user.interrupt", "processed_at": "2026-11-26T00:00:00Z"},
                {"type": "session.status_idle", "stop_reason": {"type": "interrupted"}},
            ]})
        return httpx.Response(404)
    runtime = ManagedAgentsRuntime(
        config(), client_factory=lambda: httpx.Client(base_url="https://api.anthropic.com",
            transport=httpx.MockTransport(handler)),
        sleep=lambda _seconds: None,
    )
    with pytest.raises(RuntimePaused):
        runtime.start(request(
            external_run_id="sesn_pause_recover", attempt_number=2,
            request_metadata={"control_request": {
                "action": "pause", "interrupt_event_id": "evt_interrupt_saved",
            }},
            control_check=lambda: "pause",
        ))
    assert ("POST", "/v1/sessions/sesn_pause_recover/events") not in calls


def test_ambiguous_managed_agent_session_create_requires_manual_reconciliation():
    calls = []

    def handler(req):
        calls.append((req.method, req.url.path))
        if req.method == "GET" and req.url.path == "/v1/agents/agent_test":
            return httpx.Response(200, json={"id": "agent_test", "archived_at": None,
                "tools": [], "mcp_servers": [], "skills": [], "multiagent": None})
        if req.method == "POST" and req.url.path == "/v1/sessions":
            # A gateway error does not prove that the provider failed to create
            # the session; retrying could create a second billable session.
            return httpx.Response(503, json={"error": "upstream timeout"})
        return httpx.Response(404)

    runtime = ManagedAgentsRuntime(
        config(),
        client_factory=lambda: httpx.Client(
            base_url="https://api.anthropic.com",
            transport=httpx.MockTransport(handler),
        ),
        sleep=lambda _seconds: None,
    )

    with pytest.raises(RuntimeManualReviewRequired, match="session creation"):
        runtime.start(request())

    assert calls == [
        ("GET", "/v1/agents/agent_test"),
        ("POST", "/v1/sessions"),
    ]


def test_managed_agent_created_session_must_be_persisted_before_polling():
    calls = []

    def handler(req):
        calls.append((req.method, req.url.path))
        if req.method == "GET" and req.url.path == "/v1/agents/agent_test":
            return httpx.Response(200, json={"id": "agent_test", "archived_at": None,
                "tools": [], "mcp_servers": [], "skills": [], "multiagent": None})
        if req.method == "POST" and req.url.path == "/v1/sessions":
            return httpx.Response(200, json={"id": "sesn_created"})
        return httpx.Response(404)

    def fail_persistence(_session_id):
        raise RuntimeError("database connection lost")

    runtime = ManagedAgentsRuntime(
        config(),
        client_factory=lambda: httpx.Client(
            base_url="https://api.anthropic.com",
            transport=httpx.MockTransport(handler),
        ),
        sleep=lambda _seconds: None,
    )

    with pytest.raises(RuntimeManualReviewRequired, match="persist"):
        runtime.start(request(persist_external_run_id=fail_persistence))

    assert calls == [
        ("GET", "/v1/agents/agent_test"),
        ("POST", "/v1/sessions"),
    ]


def test_malformed_managed_agent_session_create_response_requires_manual_review():
    def handler(req):
        if req.method == "GET" and req.url.path == "/v1/agents/agent_test":
            return httpx.Response(200, json={"id": "agent_test", "archived_at": None,
                "tools": [], "mcp_servers": [], "skills": [], "multiagent": None})
        if req.method == "POST" and req.url.path == "/v1/sessions":
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    runtime = ManagedAgentsRuntime(
        config(),
        client_factory=lambda: httpx.Client(
            base_url="https://api.anthropic.com",
            transport=httpx.MockTransport(handler),
        ),
        sleep=lambda _seconds: None,
    )

    with pytest.raises(RuntimeManualReviewRequired, match="malformed"):
        runtime.start(request())


def _mcp_config(**overrides):
    values = {
        "claude_managed_mcp_enabled": True,
        "claude_managed_mcp_public_base_url": "https://mcp.example.test",
        "claude_managed_mcp_vault_id": "vlt_test",
        "claude_managed_mcp_enabled_tool_keys": "system.health.read",
        "claude_managed_mcp_requests_per_minute": 120,
        "claude_managed_mcp_max_concurrent_requests": 8,
        "claude_managed_mcp_max_request_body_bytes": 1048576,
    }
    values.update(overrides)
    return config(**values)


def _mcp_request(**overrides):
    values = {
        "prepare_mcp_session": lambda: {
            "session_id": "a1b2c3d4-e5f6-4789-9012-1234567890ab",
            "credential_id": "b1b2c3d4-e5f6-4789-9012-1234567890ab",
            "token": "aos_ms_b1b2c3d4-e5f6-4789-9012-1234567890ab." + ("x" * 43),
            "expires_at": "2026-11-28T12:00:00+00:00",
        },
        "persist_mcp_provider_credential": lambda *_args: None,
        "revoke_mcp_session_credential": lambda *_args: None,
        "mark_mcp_provider_credential_archived": lambda *_args: None,
    }
    values.update(overrides)
    return request(**values)


def test_managed_agents_creates_session_scoped_vault_mcp_credential_and_archives_on_success():
    seen = []
    persisted = []
    revoked = []
    archived = []
    mcp_url = "https://mcp.example.test/v1/integrations/claude/mcp/sessions/a1b2c3d4-e5f6-4789-9012-1234567890ab"
    metadata = {
        "agency_os_execution_id": "exec-test",
        "agency_os_session_id": "a1b2c3d4-e5f6-4789-9012-1234567890ab",
        "agency_os_mcp_server_url": mcp_url,
    }

    def handler(req):
        seen.append((req.method, req.url.path))
        if req.method == "GET" and req.url.path == "/v1/agents/agent_test":
            return httpx.Response(200, json={
                "id": "agent_test", "archived_at": None,
                "tools": [], "mcp_servers": [], "skills": [], "multiagent": None,
            })
        if req.method == "GET" and req.url.path == "/v1/environments/env_test":
            return httpx.Response(200, json={
                "id": "env_test", "archived_at": None,
                "config": {"type": "cloud", "networking": {
                    "type": "limited", "allow_mcp_servers": False,
                    "allowed_hosts": ["mcp.example.test"],
                }},
            })
        if req.method == "POST" and req.url.path == "/v1/vaults/vlt_test/credentials":
            body = json.loads(req.content)
            assert body["auth"] == {
                "type": "static_bearer",
                "token": _mcp_request().prepare_mcp_session()["token"],
                "mcp_server_url": mcp_url,
            }
            assert body["metadata"] == metadata
            return httpx.Response(200, json={
                "id": "vcrd_test", "archived_at": None,
                "auth": {"type": "static_bearer", "mcp_server_url": mcp_url},
                "metadata": metadata,
            })
        if req.method == "POST" and req.url.path == "/v1/sessions":
            body = json.loads(req.content)
            assert body["vault_ids"] == ["vlt_test"]
            assert body["agent"]["type"] == "agent_with_overrides"
            assert body["agent"]["id"] == "agent_test"
            assert body["agent"]["mcp_servers"] == [{
                "type": "url", "name": "agency_os", "url": mcp_url,
            }]
            toolset = next(item for item in body["agent"]["tools"] if item["type"] == "mcp_toolset")
            assert toolset["mcp_server_name"] == "agency_os"
            assert toolset["default_config"]["enabled"] is False
            assert toolset["configs"] == [{
                "name": "system.health.read", "enabled": True,
                "permission_policy": {"type": "always_allow"},
            }]
            serialized = json.dumps(body)
            assert "aos_ms_" not in serialized
            return httpx.Response(200, json={"id": "sesn_mcp", "status": "running"})
        if req.method == "GET" and req.url.path == "/v1/sessions/sesn_mcp":
            return httpx.Response(200, json={"id": "sesn_mcp", "status": "idle"})
        if req.method == "GET" and req.url.path == "/v1/sessions/sesn_mcp/events":
            return httpx.Response(200, json={"data": [
                {"type": "agent.message", "content": [{"type": "text", "text": "MCP work completed."}]},
                {"type": "session.status_idle", "stop_reason": {"type": "end_turn"}},
            ]})
        if req.method == "POST" and req.url.path == "/v1/vaults/vlt_test/credentials/vcrd_test/archive":
            return httpx.Response(200, json={"id": "vcrd_test", "archived_at": "2026-11-28T11:00:00Z"})
        return httpx.Response(404)

    runtime = ManagedAgentsRuntime(
        _mcp_config(),
        client_factory=lambda: httpx.Client(
            base_url="https://api.anthropic.com",
            transport=httpx.MockTransport(handler),
        ),
        sleep=lambda _seconds: None,
    )
    result = runtime.start(_mcp_request(
        persist_mcp_provider_credential=lambda *args: persisted.append(args),
        revoke_mcp_session_credential=lambda *args: revoked.append(args),
        mark_mcp_provider_credential_archived=lambda *args: archived.append(args),
    ))
    assert result.detail == "MCP work completed."
    assert persisted == [(
        "b1b2c3d4-e5f6-4789-9012-1234567890ab",
        "vlt_test",
        "vcrd_test",
    )]
    assert revoked == [("b1b2c3d4-e5f6-4789-9012-1234567890ab", "MCP_SESSION_COMPLETED")]
    assert archived == [("b1b2c3d4-e5f6-4789-9012-1234567890ab", "vcrd_test")]
    assert ("POST", "/v1/vaults/vlt_test/credentials/vcrd_test/archive") in seen


def test_managed_agents_reconciles_ambiguous_vault_create_without_duplicate_post():
    calls = []
    mcp_url = "https://mcp.example.test/v1/integrations/claude/mcp/sessions/a1b2c3d4-e5f6-4789-9012-1234567890ab"
    metadata = {
        "agency_os_execution_id": "exec-test",
        "agency_os_session_id": "a1b2c3d4-e5f6-4789-9012-1234567890ab",
        "agency_os_mcp_server_url": mcp_url,
    }

    def handler(req):
        calls.append((req.method, req.url.path))
        if req.method == "GET" and req.url.path == "/v1/agents/agent_test":
            return httpx.Response(200, json={"id": "agent_test", "archived_at": None, "tools": [], "mcp_servers": [], "skills": [], "multiagent": None})
        if req.method == "GET" and req.url.path == "/v1/environments/env_test":
            return httpx.Response(200, json={"config": {"type": "cloud", "networking": {
                "type": "limited", "allow_mcp_servers": False, "allowed_hosts": ["mcp.example.test"],
            }}})
        if req.method == "POST" and req.url.path == "/v1/vaults/vlt_test/credentials":
            return httpx.Response(503, json={"error": "temporary"})
        if req.method == "GET" and req.url.path == "/v1/vaults/vlt_test/credentials":
            return httpx.Response(200, json={"data": [{
                "id": "vcrd_reconciled", "archived_at": None,
                "auth": {"type": "static_bearer", "mcp_server_url": mcp_url},
                "metadata": metadata,
            }], "next_page": None})
        if req.method == "POST" and req.url.path == "/v1/sessions":
            body = json.loads(req.content)
            assert body["vault_ids"] == ["vlt_test"]
            return httpx.Response(200, json={"id": "sesn_reconciled", "status": "running"})
        if req.method == "GET" and req.url.path == "/v1/sessions/sesn_reconciled":
            return httpx.Response(200, json={"id": "sesn_reconciled", "status": "idle"})
        if req.method == "GET" and req.url.path == "/v1/sessions/sesn_reconciled/events":
            return httpx.Response(200, json={"data": [
                {"type": "agent.message", "content": [{"type": "text", "text": "Recovered MCP create."}]},
                {"type": "session.status_idle", "stop_reason": {"type": "end_turn"}},
            ]})
        if req.method == "POST" and req.url.path.endswith("/vcrd_reconciled/archive"):
            return httpx.Response(200, json={"id": "vcrd_reconciled"})
        return httpx.Response(404)

    persisted = []
    runtime = ManagedAgentsRuntime(
        _mcp_config(),
        client_factory=lambda: httpx.Client(base_url="https://api.anthropic.com", transport=httpx.MockTransport(handler)),
        sleep=lambda _seconds: None,
    )
    result = runtime.start(_mcp_request(persist_mcp_provider_credential=lambda *args: persisted.append(args)))
    assert result.detail == "Recovered MCP create."
    assert calls.count(("POST", "/v1/vaults/vlt_test/credentials")) == 1
    assert persisted[0][2] == "vcrd_reconciled"


def test_managed_agents_rejects_mcp_environment_with_unrestricted_server_networking():
    calls = []

    def handler(req):
        calls.append((req.method, req.url.path))
        if req.method == "GET" and req.url.path == "/v1/agents/agent_test":
            return httpx.Response(200, json={"id": "agent_test", "archived_at": None, "tools": [], "mcp_servers": [], "skills": [], "multiagent": None})
        if req.method == "GET" and req.url.path == "/v1/environments/env_test":
            return httpx.Response(200, json={"config": {"type": "cloud", "networking": {
                "type": "limited", "allow_mcp_servers": True, "allowed_hosts": ["mcp.example.test"],
            }}})
        return httpx.Response(404)

    runtime = ManagedAgentsRuntime(
        _mcp_config(),
        client_factory=lambda: httpx.Client(base_url="https://api.anthropic.com", transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(RuntimeNotConfiguredError):
        runtime.start(_mcp_request())
    assert calls == [
        ("GET", "/v1/agents/agent_test"),
        ("GET", "/v1/environments/env_test"),
    ]


def test_managed_agents_reconciles_orphaned_vault_credential_and_never_creates_second_session():
    calls = []
    os_session_id = "a1b2c3d4-e5f6-4789-9012-1234567890ab"
    os_credential_id = "b1b2c3d4-e5f6-4789-9012-1234567890ab"
    mcp_url = f"https://mcp.example.test/v1/integrations/claude/mcp/sessions/{os_session_id}"
    metadata = {
        "agency_os_execution_id": "exec-test",
        "agency_os_session_id": os_session_id,
        "agency_os_mcp_server_url": mcp_url,
    }

    def handler(req):
        calls.append((req.method, req.url.path))
        if req.method == "GET" and req.url.path == "/v1/agents/agent_test":
            return httpx.Response(200, json={"id": "agent_test", "archived_at": None, "tools": [], "mcp_servers": [], "skills": [], "multiagent": None})
        if req.method == "GET" and req.url.path == "/v1/environments/env_test":
            return httpx.Response(200, json={"config": {"type": "cloud", "networking": {
                "type": "limited", "allow_mcp_servers": False, "allowed_hosts": ["mcp.example.test"],
            }}})
        if req.method == "GET" and req.url.path == "/v1/vaults/vlt_test/credentials":
            return httpx.Response(200, json={"data": [{
                "id": "vcrd_orphan", "archived_at": None,
                "auth": {"type": "static_bearer", "mcp_server_url": mcp_url},
                "metadata": metadata,
            }], "next_page": None})
        if req.method == "POST" and req.url.path == "/v1/vaults/vlt_test/credentials/vcrd_orphan/archive":
            return httpx.Response(200, json={"id": "vcrd_orphan"})
        return httpx.Response(404)

    persisted = []
    revoked = []
    archived = []
    runtime = ManagedAgentsRuntime(
        _mcp_config(),
        client_factory=lambda: httpx.Client(base_url="https://api.anthropic.com", transport=httpx.MockTransport(handler)),
        sleep=lambda _seconds: None,
    )
    with pytest.raises(RuntimeManualReviewRequired, match="interrupted provider create"):
        runtime.start(_mcp_request(
            get_mcp_provider_credential=lambda: {
                "credential_id": os_credential_id,
                "session_id": os_session_id,
                "vault_id": None,
                "provider_credential_id": None,
            },
            persist_mcp_provider_credential=lambda *args: persisted.append(args),
            revoke_mcp_session_credential=lambda *args: revoked.append(args),
            mark_mcp_provider_credential_archived=lambda *args: archived.append(args),
        ))
    assert ("POST", "/v1/sessions") not in calls
    assert ("POST", "/v1/vaults/vlt_test/credentials") not in calls
    assert persisted == [(os_credential_id, "vlt_test", "vcrd_orphan")]
    assert revoked == [(os_credential_id, "MCP_ORPHANED_CREDENTIAL")]
    assert archived == [(os_credential_id, "vcrd_orphan")]


def test_managed_agents_extracts_normalized_session_usage():
    runtime = ManagedAgentsRuntime(config(), client_factory=lambda: None, sleep=lambda _seconds: None)
    events = [
        {"type": "agent.message", "content": [{"type": "text", "text": "Completed."}]},
        {"type": "session.usage", "usage": {
            "input_tokens": 120, "output_tokens": 45, "cache_read_input_tokens": 20,
            "cache_creation": {"ephemeral_5m_input_tokens": 6, "ephemeral_1h_input_tokens": 4},
            "list_cost": {"amount": "7", "currency": "USD"},
            "active_seconds": 12.5,
            "server_tool_use": {"web_search_requests": 1, "web_fetch_requests": 0},
        }},
        {"type": "session.status_idle", "stop_reason": {"type": "end_turn"}},
    ]
    result = runtime._extract_result(events, "sesn_usage")
    assert result.usage == {
        "input_tokens": 120, "output_tokens": 45, "cache_read_input_tokens": 20,
        "cache_creation_input_tokens": 10, "list_cost_minor": 7, "currency": "USD",
        "active_seconds": 12.5, "server_tool_use": {"web_search_requests": 1, "web_fetch_requests": 0},
    }


def test_managed_agents_preserves_usage_when_session_reaches_budget():
    runtime = ManagedAgentsRuntime(config(), client_factory=lambda: None, sleep=lambda _seconds: None)
    usage = {"input_tokens": 100, "output_tokens": 50, "list_cost": {"amount": "251", "currency": "USD"}}
    events = [
        {"type": "agent.message", "content": [{"type": "text", "text": "Budget reached."}]},
        {"type": "session.usage", "usage": usage},
        {"type": "session.status_idle", "stop_reason": {"type": "budget_reached"}},
    ]
    with pytest.raises(RuntimeManualReviewRequired) as error:
        runtime._extract_result(events, "sesn_budget")
    assert error.value.usage == {
        "input_tokens": 100, "output_tokens": 50, "list_cost_minor": 251, "currency": "USD",
    }


def test_managed_agents_rejects_malformed_or_non_usd_usage():
    runtime = ManagedAgentsRuntime(config(), client_factory=lambda: None, sleep=lambda _seconds: None)
    events = [
        {"type": "agent.message", "content": [{"type": "text", "text": "Completed."}]},
        {"type": "session.usage", "usage": {"list_cost": {"amount": "1.5", "currency": "USD"}}},
        {"type": "session.status_idle", "stop_reason": {"type": "end_turn"}},
    ]
    with pytest.raises(RuntimeManualReviewRequired):
        runtime._extract_result(events, "sesn_bad_usage")
