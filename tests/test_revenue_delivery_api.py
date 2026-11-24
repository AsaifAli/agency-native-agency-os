import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import Principal, get_principal
from app.db import Base, get_db
from app.domain_routes import router
from app.models import Membership, Organization, Role, User, Workspace
from app.domain_models import Client
import app.domain_models  # noqa: F401


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    db = TestingSession()
    user = User(email="domain-owner@example.test", display_name="Owner")
    org = Organization(name="Domain Test Org")
    other_org = Organization(name="Other Org")
    db.add_all([user, org, other_org])
    db.flush()
    ws = Workspace(id="domain-ws", org_id=org.id, name="Workspace")
    other_ws = Workspace(id="other-ws", org_id=other_org.id, name="Other")
    db.add_all([ws, other_ws])
    db.add(Membership(org_id=org.id, user_id=user.id, role=Role.owner))
    db.flush()
    foreign_client = Client(
        org_id=other_org.id, workspace_id=other_ws.id,
        name="Foreign client", created_by=user.id,
    )
    db.add(foreign_client)
    db.commit()

    app = FastAPI()
    app.include_router(router)

    def override_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_principal] = lambda: Principal(user=user)
    test_client = TestClient(app)
    test_client.org_id = org.id
    test_client.ws_id = ws.id
    test_client.other_ws_id = other_ws.id
    test_client.foreign_client_id = foreign_client.id
    yield test_client
    db.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def auth():
    return {"Authorization": "Bearer test"}


def test_revenue_delivery_vertical_slice_and_audit(client):
    org, ws = client.org_id, client.ws_id
    r = client.post(f"/v1/orgs/{org}/clients", headers=auth(), json={
        "workspace_id": ws, "name": "Acme Industries", "external_key": "acme-01"
    })
    assert r.status_code == 201, r.text
    client_id = r.json()["id"]

    # Nullable external keys must not prevent multiple manually-created clients.
    r2 = client.post(f"/v1/orgs/{org}/clients", headers=auth(), json={
        "workspace_id": ws, "name": "Second Acme"
    })
    assert r2.status_code == 201, r2.text

    r = client.post(f"/v1/orgs/{org}/contacts", headers=auth(), json={
        "workspace_id": ws, "client_id": client_id,
        "first_name": "Asha", "email": "ASHA@example.test",
        "consent_status": "granted"
    })
    assert r.status_code == 201, r.text
    contact_id = r.json()["id"]
    assert r.json()["email"] == "asha@example.test"

    r = client.post(f"/v1/orgs/{org}/leads", headers=auth(), json={
        "workspace_id": ws, "client_id": client_id, "contact_id": contact_id,
        "company_name": "Acme Industries", "score": 82, "source": "referral"
    })
    assert r.status_code == 201, r.text
    lead_id = r.json()["id"]

    r = client.patch(f"/v1/orgs/{org}/leads/{lead_id}", headers=auth(), json={
        "stage": "qualified"
    })
    assert r.status_code == 200, r.text
    assert r.json()["stage"] == "qualified"

    r = client.post(f"/v1/orgs/{org}/opportunities", headers=auth(), json={
        "workspace_id": ws, "client_id": client_id, "lead_id": lead_id,
        "title": "AI workflow engagement", "amount_minor": 2500000,
        "currency": "INR", "probability": 60
    })
    assert r.status_code == 201, r.text
    opportunity_id = r.json()["id"]

    r = client.post(f"/v1/orgs/{org}/projects", headers=auth(), json={
        "workspace_id": ws, "client_id": client_id,
        "opportunity_id": opportunity_id, "name": "Discovery and implementation"
    })
    assert r.status_code == 201, r.text
    project_id = r.json()["id"]

    r = client.post(f"/v1/orgs/{org}/milestones", headers=auth(), json={
        "workspace_id": ws, "project_id": project_id, "title": "Discovery"
    })
    assert r.status_code == 201, r.text
    milestone_id = r.json()["id"]

    r = client.patch(f"/v1/orgs/{org}/milestones/{milestone_id}", headers=auth(), json={
        "status": "completed"
    })
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed"


def test_cross_workspace_parent_reference_is_rejected(client):
    org, ws, other_ws = client.org_id, client.ws_id, client.other_ws_id
    # A real client in another organization/workspace must not be attachable.
    r = client.post(f"/v1/orgs/{org}/contacts", headers=auth(), json={
        "workspace_id": ws, "client_id": client.foreign_client_id,
        "first_name": "Nope"
    })
    assert r.status_code == 404
