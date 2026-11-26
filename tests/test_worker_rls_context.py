from types import SimpleNamespace

import pytest

from app.db import (
    scoped_worker_capability_session_factory,
    scoped_worker_workspace_session_factory,
)


class FakeSession:
    def __init__(self):
        self.info = {}

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))


def test_execution_capability_factory_sets_only_private_capability_context():
    sessions = []

    def factory():
        session = FakeSession()
        sessions.append(session)
        return session

    capability = SimpleNamespace(
        token=b"x" * 32, execution_id="exec-1", attempt_id="attempt-1",
        worker_id="worker-1", lease_generation=1,
    )
    session = scoped_worker_capability_session_factory(capability, factory)()

    assert session is sessions[0]
    assert session.info["agency_os_worker_capability"] is capability
    assert "agency_os_rls_context" not in session.info


def test_workspace_capability_factory_sets_only_private_capability_context():
    sessions = []

    def factory():
        session = FakeSession()
        sessions.append(session)
        return session

    capability = SimpleNamespace(
        token=b"x" * 32, org_id="org-1", workspace_id="workspace-1",
        worker_id="worker-1",
    )
    session = scoped_worker_workspace_session_factory(capability, factory)()

    assert session is sessions[0]
    assert session.info["agency_os_worker_workspace_capability"] is capability
    assert "agency_os_rls_context" not in session.info


@pytest.mark.parametrize("factory", [
    scoped_worker_capability_session_factory,
    scoped_worker_workspace_session_factory,
])
def test_capability_factories_reject_incomplete_capabilities(factory):
    with pytest.raises(ValueError, match="capability"):
        factory(SimpleNamespace(), lambda: FakeSession())
