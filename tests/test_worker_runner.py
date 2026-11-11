
from unittest.mock import Mock

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

    monkeypatch.setattr(runner, "promote_due_retries", promote)
    monkeypatch.setattr(
        runner,
        "recover_expired_execution_leases",
        recover,
    )

    promoted, recovered = runner._run_maintenance(
        session_factory=session_factory,
        batch_size=25,
    )

    assert (promoted, recovered) == (2, 3)
    assert len(sessions) == 2
    assert all(session.committed for session in sessions)
    assert all(session.closed for session in sessions)
    promote.assert_called_once_with(sessions[0], limit=25)
    recover.assert_called_once_with(sessions[1], limit=25)


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

    monkeypatch.setattr(runner, "promote_due_retries", promote)
    monkeypatch.setattr(
        runner,
        "recover_expired_execution_leases",
        recover,
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
    assert len(sessions) == 2
    assert all(session.committed for session in sessions)


def test_run_worker_propagates_processor_failure(monkeypatch):
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
