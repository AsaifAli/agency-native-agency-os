import json
from types import SimpleNamespace

import httpx
import pytest

from app.integrations.managed_agents import ManagedAgentsRuntime
from app.integrations.runtime import (
    ExecutionRequest,
    RuntimeCancelled,
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
