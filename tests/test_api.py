import os
os.environ["DATABASE_URL"] = "sqlite:///./test_agency_os.db"
os.environ["DEV_AUTH_ENABLED"] = "true"
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, engine, SessionLocal
from app.models import User, Organization, Membership, Workspace, Role

def setup_module():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    user = User(email="owner@test.local", display_name="Owner")
    org = Organization(name="Test Org")
    db.add_all([user, org]); db.flush()
    db.add(Membership(org_id=org.id, user_id=user.id, role=Role.owner))
    db.add(Workspace(id="ws-test", org_id=org.id, name="Test Workspace"))
    db.commit()
    db.close()

def test_tenant_scoped_workspace_list():
    client = TestClient(app)
    response = client.get("/v1/orgs/" + _org_id() + "/workspaces",
                          headers={"Authorization": "Bearer dev:owner@test.local"})
    assert response.status_code == 200
    assert response.json()[0]["id"] == "ws-test"

def _org_id():
    db = SessionLocal()
    try:
        return db.query(Organization).filter_by(name="Test Org").one().id
    finally:
        db.close()
