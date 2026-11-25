
import importlib
import signal
from unittest.mock import Mock

import pytest

worker_main = importlib.import_module("app.worker.main")


def test_main_handles_shutdown_signal_and_disposes_engine(monkeypatch):
    signal_registration = Mock()
    run_worker = Mock()
    dispose = Mock()

    monkeypatch.setattr(
        worker_main.signal,
        "signal",
        signal_registration,
    )
    monkeypatch.setattr(worker_main, "run_worker", run_worker)
    monkeypatch.setattr(worker_main.worker_engine, "dispose", dispose)
    monkeypatch.setattr(
        worker_main.socket,
        "gethostname",
        lambda: "test-host",
    )
    monkeypatch.setattr(
        worker_main.uuid,
        "uuid4",
        lambda: type("UUID", (), {"hex": "test-id"})(),
    )

    def stop_worker(stop_event, worker_id):
        assert worker_id == "test-host:test-id"
        term_handler = next(
            args[1]
            for args, kwargs in signal_registration.call_args_list
            if args[0] == signal.SIGTERM
        )
        term_handler(signal.SIGTERM, None)
        assert stop_event.is_set()

    run_worker.side_effect = stop_worker

    worker_main.main()

    assert signal_registration.call_count == 2
    run_worker.assert_called_once()
    dispose.assert_called_once()


def test_main_disposes_engine_when_worker_fails(monkeypatch):
    monkeypatch.setattr(worker_main.signal, "signal", Mock())
    monkeypatch.setattr(
        worker_main,
        "run_worker",
        Mock(side_effect=RuntimeError("simulated failure")),
    )
    dispose = Mock()
    monkeypatch.setattr(worker_main.worker_engine, "dispose", dispose)

    with pytest.raises(RuntimeError, match="simulated failure"):
        worker_main.main()

    dispose.assert_called_once()
