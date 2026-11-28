
from unittest.mock import Mock
from types import SimpleNamespace

import pytest

from app.worker import runner


class FakeSession:
    def __init__(self):
        self.committed = False
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.closed = True
        return False

    def commit(self):
        self.committed = True

    def execute(self, statement, params=None):
        class Result:
            def scalar_one(self):
                return 0
        return Result()


class StopAfterWait:
    def __init__(self):
        self.stopped = False
        self.waited_for = []

    def is_set(self):
        return self.stopped

    def wait(self, timeout):
        self.waited_for.append(timeout)
        self.stopped = True
        return True


def test_run_maintenance_commits_separate_transactions(monkeypatch):
    sessions = []

    def session_factory():
        session = FakeSession()
        sessions.append(session)
        return session

    promote = Mock(return_value=2)
    recover = Mock(return_value=3)
    queue = Mock(return_value=4)

    monkeypatch.setattr(runner, "promote_due_retries", promote)
    monkeypatch.setattr(
        runner,
        "recover_expired_execution_leases",
        recover,
    )
    monkeypatch.setattr(runner, "queue_ready_delegations", queue)

    promoted, recovered, queued = runner._run_maintenance(
        session_factory=session_factory,
        batch_size=25,
    )

    assert (promoted, recovered, queued) == (2, 3, 4)
    assert len(sessions) == 2
    assert all(session.committed for session in sessions)
    assert all(session.closed for session in sessions)
    promote.assert_called_once_with(sessions[0], limit=25)
    recover.assert_called_once_with(sessions[1], limit=25)
    queue.assert_called_once_with(sessions[1], limit=25)


def test_run_worker_runs_startup_maintenance_and_waits_when_idle(
    monkeypatch,
):
    sessions = []

    def session_factory():
        session = FakeSession()
        sessions.append(session)
        return session

    promote = Mock(return_value=0)
    recover = Mock(return_value=0)
    queue = Mock(return_value=0)

    from types import SimpleNamespace
    capability = SimpleNamespace(
        org_id="org-1", workspace_id="workspace-1", token=b"x" * 32,
        worker_id="test-worker", lease_seconds=120,
    )
    class NoopMaintenanceHeartbeat:
        def __init__(self, session_factory, lease_seconds):
            self.session_factory = session_factory
            self.lease_seconds = lease_seconds
        def start(self):
            return None
        def assert_healthy(self):
            return None
        def stop(self):
            return None
    monkeypatch.setattr(runner, "MaintenanceLeaseHeartbeat", NoopMaintenanceHeartbeat)
    monkeypatch.setattr(runner, "claim_worker_maintenance_scope", Mock(side_effect=[capability, None]))
    monkeypatch.setattr(runner, "scoped_worker_workspace_session_factory", lambda capability, factory: factory)
    release_scope = Mock()
    monkeypatch.setattr(runner, "_release_maintenance_scope", release_scope)
    monkeypatch.setattr(runner, "promote_due_retries", promote)
    monkeypatch.setattr(
        runner,
        "recover_expired_execution_leases",
        recover,
    )
    monkeypatch.setattr(runner, "queue_ready_delegations", queue)
    expire_sessions = Mock(return_value=0)
    monkeypatch.setattr(runner, "expire_due_agent_sessions", expire_sessions)
    purge_retention = Mock(return_value={
        "agent_sessions_scrubbed": 0,
        "tool_payloads_purged": 0,
    })
    monkeypatch.setattr(runner, "purge_due_retention_data", purge_retention)

    monkeypatch.setattr(
        runner,
        "reconcile_outbox_events",
        Mock(return_value=(0, 0)),
    )

    stop_event = StopAfterWait()
    processor = Mock(return_value=None)

    runner.run_worker(
        stop_event=stop_event,
        worker_id="test-worker",
        session_factory=session_factory,
        processor=processor,
        lease_seconds=60,
        poll_interval_seconds=0.5,
        maintenance_interval_seconds=15,
        maintenance_batch_size=10,
        clock=lambda: 100.0,
    )

    promote.assert_called_once()
    recover.assert_called_once()
    processor.assert_called_once_with(
        worker_id="test-worker",
        lease_seconds=60,
        session_factory=session_factory,
    )
    assert stop_event.waited_for == [0.5]
    assert runner.claim_worker_maintenance_scope.call_count == 2
    assert runner.claim_worker_maintenance_scope.call_args_list[0].kwargs["after_workspace_id"] is None
    assert runner.claim_worker_maintenance_scope.call_args_list[1].kwargs["after_workspace_id"] == "workspace-1"
    release_scope.assert_called_once()
    assert len(sessions) == 8
    assert all(session.committed for session in sessions)
    expire_sessions.assert_called_once_with(sessions[3], limit=10)
    purge_retention.assert_called_once_with(
        sessions[4],
        limit=10,
        agent_session_days=runner.settings.agent_session_metadata_retention_days,
        tool_invocation_payload_days=runner.settings.tool_invocation_payload_retention_days,
    )
    assert sessions[5].committed  # outbox reconciliation
    assert sessions[7].committed  # bounded SECURITY DEFINER browser-session retention


def test_run_worker_propagates_processor_failure(monkeypatch):
    monkeypatch.setattr(runner, "claim_worker_maintenance_scope", Mock(return_value=None))
    monkeypatch.setattr(
        runner,
        "promote_due_retries",
        Mock(return_value=0),
    )
    monkeypatch.setattr(
        runner,
        "recover_expired_execution_leases",
        Mock(return_value=0),
    )
    monkeypatch.setattr(runner, "queue_ready_delegations", Mock(return_value=0))
    monkeypatch.setattr(runner, "expire_due_agent_sessions", Mock(return_value=0))

    monkeypatch.setattr(
        runner,
        "reconcile_outbox_events",
        Mock(return_value=(0, 0)),
    )

    stop_event = StopAfterWait()

    def failing_processor(**kwargs):
        raise RuntimeError("simulated worker failure")

    with pytest.raises(RuntimeError, match="simulated worker failure"):
        runner.run_worker(
            stop_event=stop_event,
            worker_id="test-worker",
            session_factory=FakeSession,
            processor=failing_processor,
            clock=lambda: 100.0,
        )

    assert stop_event.waited_for == []


def test_run_worker_rejects_invalid_worker_id():
    with pytest.raises(ValueError, match="worker_id"):
        runner.run_worker(
            stop_event=StopAfterWait(),
            worker_id=" ",
            processor=Mock(),
        )


def test_outbox_reconciliation_runs_without_registered_handlers(monkeypatch):
    sessions = []
    reconcile = Mock(return_value=(3, 2))
    dispatch = Mock(return_value=(0, 0, 0))

    def session_factory():
        session = FakeSession()
        sessions.append(session)
        return session

    monkeypatch.setattr(runner, "OUTBOX_HANDLERS", {})
    monkeypatch.setattr(runner, "reconcile_outbox_events", reconcile)
    monkeypatch.setattr(runner, "dispatch_outbox_batch", dispatch)

    result = runner._run_outbox_maintenance(
        session_factory,
        worker_id="test-worker",
        batch_size=25,
    )

    assert result == (0, 0, 2, 3)
    assert len(sessions) == 1
    assert sessions[0].committed
    assert sessions[0].closed
    reconcile.assert_called_once_with(sessions[0], limit=25)
    dispatch.assert_not_called()


def test_outbox_dispatch_runs_after_reconciliation_when_handlers_exist(
    monkeypatch,
):
    sessions = []
    handler = Mock()
    handlers = {"test.event": handler}
    reconcile = Mock(return_value=(1, 0))
    dispatch = Mock(return_value=(4, 2, 1))

    def session_factory():
        session = FakeSession()
        sessions.append(session)
        return session

    monkeypatch.setattr(runner, "OUTBOX_HANDLERS", handlers)
    monkeypatch.setattr(runner, "reconcile_outbox_events", reconcile)
    monkeypatch.setattr(runner, "dispatch_outbox_batch", dispatch)

    result = runner._run_outbox_maintenance(
        session_factory,
        worker_id="test-worker",
        batch_size=25,
    )

    assert result == (4, 2, 1, 1)
    assert len(sessions) == 1
    assert sessions[0].committed
    dispatch.assert_called_once()
    assert dispatch.call_args.kwargs["handlers"] is handlers


def test_session_maintenance_commits_expiry_batch(monkeypatch):
    sessions = []
    expired = Mock(return_value=4)

    def session_factory():
        session = FakeSession()
        sessions.append(session)
        return session

    monkeypatch.setattr(runner, "expire_due_agent_sessions", expired)
    assert runner._run_session_maintenance(session_factory, batch_size=25) == 4
    assert len(sessions) == 1
    assert sessions[0].committed and sessions[0].closed
    expired.assert_called_once_with(sessions[0], limit=25)


def test_production_worker_verifies_its_nobypassrls_database_role(monkeypatch):
    verification = Mock()
    monkeypatch.setattr(runner.settings, "app_env", "production")
    monkeypatch.setattr(runner.settings, "process_role", "worker")
    monkeypatch.setattr(runner, "worker_engine", SimpleNamespace(dialect=SimpleNamespace(name="postgresql")))
    monkeypatch.setattr(runner, "verify_postgres_role", verification)

    runner._verify_worker_database_role()

    verification.assert_called_once_with(
        runner.worker_engine, expected_bypassrls=False, require_rls=True,
        expected_role="agency_os_worker",
    )


def test_production_worker_fails_closed_for_wrong_process_role(monkeypatch):
    verification = Mock()
    monkeypatch.setattr(runner.settings, "app_env", "production")
    monkeypatch.setattr(runner.settings, "process_role", "api")
    monkeypatch.setattr(runner, "verify_postgres_role", verification)

    with pytest.raises(RuntimeError, match="PROCESS_ROLE=worker"):
        runner._verify_worker_database_role()

    verification.assert_not_called()


def test_nonproduction_worker_skips_production_database_role_verification(monkeypatch):
    verification = Mock()
    monkeypatch.setattr(runner.settings, "app_env", "test")
    monkeypatch.setattr(
        runner,
        "worker_engine",
        SimpleNamespace(dialect=SimpleNamespace(name="postgresql")),
    )
    monkeypatch.setattr(runner, "verify_postgres_role", verification)

    runner._verify_worker_database_role()

    verification.assert_not_called()


def test_production_worker_does_not_poll_when_database_role_verification_fails(monkeypatch):
    monkeypatch.setattr(runner.settings, "app_env", "production")
    monkeypatch.setattr(runner.settings, "process_role", "worker")

    def reject_role(*args, **kwargs):
        raise RuntimeError("unsafe PostgreSQL role")

    scopes = Mock()
    monkeypatch.setattr(runner, "worker_engine", SimpleNamespace(dialect=SimpleNamespace(name="postgresql")))
    monkeypatch.setattr(runner, "verify_postgres_role", reject_role)
    monkeypatch.setattr(runner, "claim_worker_maintenance_scope", scopes)

    with pytest.raises(RuntimeError, match="unsafe PostgreSQL role"):
        runner.run_worker(
            stop_event=StopAfterWait(),
            worker_id="production-worker",
            session_factory=FakeSession,
        )

    scopes.assert_not_called()



def test_provider_usage_reconciliation_runs_only_when_managed_agents_is_enabled(monkeypatch):
    runtime = object()
    monkeypatch.setattr(runner, "is_runtime_available", lambda name: name == "claude_managed_agents")
    get_runtime = Mock(return_value=runtime)
    reconcile = Mock(return_value={"reconciled": 2, "pending": 1, "skipped": 3})
    monkeypatch.setattr(runner, "get_runtime", get_runtime)
    monkeypatch.setattr(runner, "reconcile_abandoned_managed_agent_usage", reconcile)

    result = runner._run_provider_usage_reconciliation(lambda: None, batch_size=50)

    assert result == 2
    get_runtime.assert_called_once_with("claude_managed_agents")
    reconcile.assert_called_once()
    assert reconcile.call_args.kwargs["runtime"] is runtime
    assert reconcile.call_args.kwargs["limit"] == 10


def test_provider_usage_reconciliation_is_noop_when_runtime_is_disabled(monkeypatch):
    monkeypatch.setattr(runner, "is_runtime_available", lambda _name: False)
    get_runtime = Mock()
    reconcile = Mock()
    monkeypatch.setattr(runner, "get_runtime", get_runtime)
    monkeypatch.setattr(runner, "reconcile_abandoned_managed_agent_usage", reconcile)

    assert runner._run_provider_usage_reconciliation(lambda: None, batch_size=50) == 0
    get_runtime.assert_not_called()
    reconcile.assert_not_called()
