import pytest
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import Principal, get_principal
from app.db import Base, get_db
from app.machine_identity import authenticate_machine_token, authorize_tool_session, create_agent_session
from app.models import FounderAuthority, Membership, Organization, Role, User, Workspace
from app.security_models import AgentSession, MachineIdentity
from app.security_routes import router


@pytest.fixture()
def security_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    import app.security_models  # noqa: F401
    Base.metadata.create_all(engine)
    db = factory()
    founder = User(email="security-founder@example.test")
    org = Organization(name="Security Test Org")
    db.add_all([founder, org]); db.flush()
    workspace = Workspace(id="security-ws", org_id=org.id, name="Security Workspace")
    db.add_all([workspace, Membership(org_id=org.id, user_id=founder.id, role=Role.owner),
                FounderAuthority(org_id=org.id, user_id=founder.id, active=True)])
    db.commit()
    app = FastAPI()
    app.include_router(router)
    def override_db():
        session = factory()
        try: yield session
        finally: session.close()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_principal] = lambda: Principal(user=founder)
    client = TestClient(app)
    client.org_id, client.workspace_id, client.founder = org.id, workspace.id, founder
    client.factory = factory
    yield client
    db.close(); Base.metadata.drop_all(engine); engine.dispose()


def _create_identity(client, scopes=None, classes=None):
    response = client.post(f"/v1/orgs/{client.org_id}/machine-identities", json={
        "workspace_id": client.workspace_id, "name": "Research Worker",
        "subject_type": "worker", "subject_id": "research-worker",
        "scopes": scopes or ["sessions:create", "tools:invoke", "tool:research.read"],
        "allowed_data_classes": classes or ["synthetic", "public"], "ttl_days": 14,
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_machine_secret_is_returned_once_and_only_hash_is_persisted(security_client):
    issued = _create_identity(security_client)
    assert issued["token"].startswith("aos_mi_")
    db = security_client.factory()
    try:
        identity = db.get(MachineIdentity, issued["id"])
        assert issued["token"].split(".", 1)[1] not in identity.token_hash
        assert len(identity.token_hash) == 64
        assert "token_hash" not in issued
    finally:
        db.close()


def test_machine_token_authentication_and_expiry(security_client):
    issued = _create_identity(security_client)
    db = security_client.factory()
    try:
        principal = authenticate_machine_token("Bearer " + issued["token"], db)
        assert principal.identity.id == issued["id"]
        with pytest.raises(Exception):
            authenticate_machine_token("Bearer " + issued["token"] + "wrong", db)
        identity = db.get(MachineIdentity, issued["id"])
        identity.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
        with pytest.raises(Exception):
            authenticate_machine_token("Bearer " + issued["token"], db)
    finally:
        db.close()


def test_machine_session_is_workspace_scoped_and_data_class_bounded(security_client):
    issued = _create_identity(security_client)
    db = security_client.factory()
    try:
        principal = authenticate_machine_token("Bearer " + issued["token"], db)
        session = create_agent_session(db, principal, purpose="Public web research", data_class="public", ttl_seconds=600)
        db.commit()
        assert session.workspace_id == security_client.workspace_id
        assert session.data_class == "public"
        with pytest.raises(Exception):
            create_agent_session(db, principal, purpose="Confidential task", data_class="confidential", ttl_seconds=600)
    finally:
        db.close()


def test_tool_authorization_requires_identity_scope_and_active_session(security_client):
    issued = _create_identity(security_client)
    db = security_client.factory()
    try:
        principal = authenticate_machine_token("Bearer " + issued["token"], db)
        session = create_agent_session(db, principal, purpose="Research", data_class="public", ttl_seconds=600)
        db.commit()
        authorized = authorize_tool_session(db, principal, session_id=session.id, tool_key="research.read", data_class="public")
        assert authorized.id == session.id
        with pytest.raises(Exception):
            authorize_tool_session(db, principal, session_id=session.id, tool_key="crm.write", data_class="public")
        session.status = "cancelled"
        db.commit()
        with pytest.raises(Exception):
            authorize_tool_session(db, principal, session_id=session.id, tool_key="research.read", data_class="public")
    finally:
        db.close()


def test_founder_revocation_cancels_active_sessions(security_client):
    issued = _create_identity(security_client)
    db = security_client.factory()
    principal = authenticate_machine_token("Bearer " + issued["token"], db)
    session = create_agent_session(db, principal, purpose="Research", data_class="public", ttl_seconds=600)
    db.commit(); db.close()
    response = security_client.post(f"/v1/orgs/{security_client.org_id}/machine-identities/{issued['id']}/revoke")
    assert response.status_code == 200, response.text
    db = security_client.factory()
    try:
        assert db.get(MachineIdentity, issued["id"]).revoked_at is not None
        assert db.get(AgentSession, session.id).status == "cancelled"
    finally:
        db.close()


def test_machine_session_route_requires_machine_credential(security_client):
    issued = _create_identity(security_client)
    response = security_client.post("/v1/machine/sessions", json={
        "purpose": "Synthetic test", "data_class": "synthetic", "ttl_seconds": 300,
    })
    assert response.status_code == 401
    response = security_client.post("/v1/machine/sessions",
        headers={"Authorization": "Bearer " + issued["token"]},
        json={"purpose": "Synthetic test", "data_class": "synthetic", "ttl_seconds": 300},
    )
    assert response.status_code == 201, response.text
