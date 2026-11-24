import json
from types import SimpleNamespace

import httpx
import pytest

from app.integrations.managed_agents import ManagedAgentsRuntime
from app.integrations.runtime import ExecutionRequest, RuntimeManualReviewRequired, RuntimeTransientError
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
        "task_id": "task-test", "agent_id": "agent-local",
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
        if req.method == "POST" and req.url.path == "/v1/sessions":
            body = json.loads(req.content)
            assert body["agent"] == "agent_test"
            assert isinstance(body["agent"], str)
            assert "tools" not in body and "mcp_servers" not in body and "skills" not in body
            assert body["budget"]["max_list_cost"] == {"amount": "250", "currency": "USD"}
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
        client_factory=lambda: httpx.Client(base_url="https://api.anthropic.com", transport=httpx.MockTransport(handler)),
        sleep=lambda _seconds: None,
    )
    result = runtime.start(request(persist_external_run_id=persisted.append))
    assert result.provider == "claude_managed_agents"
    assert result.external_run_id == "sesn_test"
    assert result.status == "succeeded"
    assert result.detail == "Research completed."
    assert persisted == ["sesn_test"]
    assert len(seen) == 3


def test_managed_agents_resumes_persisted_session_without_creating_another():
    calls = []

    def handler(req):
        calls.append((req.method, req.url.path))
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
    assert calls == [("GET", "/v1/sessions/sesn_existing"), ("GET", "/v1/sessions/sesn_existing/events")]


def test_managed_agents_never_auto_confirms_tool_actions():
    def handler(req):
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
