from types import SimpleNamespace

import pytest

from app.db import scoped_worker_session_factory


class FakeSession:
    def __init__(self):
        self.info = {}

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))


def test_scoped_worker_factory_sets_exact_org_and_workspace_context():
    sessions = []

    def factory():
        session = FakeSession()
        sessions.append(session)
        return session

    scoped = scoped_worker_session_factory("org-123", "workspace-456", factory)
    session = scoped()

    assert session is sessions[0]
    assert session.info["agency_os_rls_context"] == {
        "user_id": "",
        "machine_org_id": "org-123",
        "machine_workspace_id": "workspace-456",
        "machine_identity_lookup_id": "",
        "browser_session_token_hash": "",
    }


@pytest.mark.parametrize(("org_id", "workspace_id"), [("", "w"), ("o", ""), ("", "")])
def test_scoped_worker_factory_rejects_incomplete_scope(org_id, workspace_id):
    with pytest.raises(ValueError, match="scope"):
        scoped_worker_session_factory(org_id, workspace_id, lambda: FakeSession())
