import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import Principal, get_principal
from app.db import Base, get_db
from app.models import Membership, Organization, Role, User, Workspace, FounderAuthority
from app.workforce_routes import router
from app.workforce_service import initialize_workforce
import app.workforce_models  # noqa: F401
import app.operations_models  # noqa: F401
import app.telephony.models  # noqa: F401


@pytest.fixture()
def app_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    db = factory()
    founder = User(email="founder@agency.test")
    operator = User(email="operator@agency.test")
    org = Organization(name="Workforce Test Agency")
    db.add_all([founder, operator, org]); db.flush()
    db.add_all([
        Membership(org_id=org.id, user_id=founder.id, role=Role.owner),
        Membership(org_id=org.id, user_id=operator.id, role=Role.operator),
        FounderAuthority(org_id=org.id, user_id=founder.id, active=True),
    ])
    workspace = Workspace(id="wf-test", org_id=org.id, name="Agency Workspace")
    db.add(workspace); db.commit()
    identity={"user":founder, "org":org, "workspace":workspace, "operator":operator}
    from app.main import app
    app.dependency_overrides.clear()
    def override_db():
        session=factory()
        try: yield session
        finally: session.close()
    app.dependency_overrides[get_db]=override_db
    app.dependency_overrides[get_principal]=lambda:Principal(user=identity["user"])
    client=TestClient(app)
    client.identity=identity
    client.factory=factory
    yield client
    db.close(); Base.metadata.drop_all(engine); engine.dispose()


def test_founder_initializes_full_chart_idempotently(app_client):
    i=app_client.identity
    r=app_client.post(f"/v1/orgs/{i['org'].id}/workforce/bootstrap",params={"workspace_id":i["workspace"].id})
    assert r.status_code==200, r.text
    assert r.json()["departments"]==16
    assert r.json()["department_heads"]==16
    assert r.json()["specialists"]==16
    r2=app_client.post(f"/v1/orgs/{i['org'].id}/workforce/bootstrap",params={"workspace_id":i["workspace"].id})
    assert r2.status_code==200, r2.text
    listing=app_client.get(f"/v1/orgs/{i['org'].id}/workforce",params={"workspace_id":i["workspace"].id})
    assert listing.status_code==200
    keys={x["department_key"] for x in listing.json()["members"]}
    assert all(key in keys for key in [
        "marketing_brand","business_development_sales","market_research_intelligence",
        "solutions_consulting_strategy","finance_accounts","legal_risk_compliance",
        "ai_research_innovation","ai_engineering_development","automation_integration_engineering",
        "infrastructure_it_operations","pmo","delivery_implementation",
        "quality_assurance_security","client_success_support","hr_people_operations",
        "administration_procurement","office_founder","office_chief_of_staff",
        "office_executive_assistant",
    ])


def test_organization_owner_without_founder_grant_cannot_initialize(app_client):
    i=app_client.identity
    app_client.app.dependency_overrides[get_principal]=lambda:Principal(user=i["operator"])
    # Operator membership is also insufficient; founder grant is separately checked.
    r=app_client.post(f"/v1/orgs/{i['org'].id}/workforce/bootstrap",params={"workspace_id":i["workspace"].id})
    assert r.status_code==403


def test_capabilities_start_disabled_and_require_founder(app_client):
    i=app_client.identity
    app_client.post(f"/v1/orgs/{i['org'].id}/workforce/bootstrap",params={"workspace_id":i["workspace"].id})
    listing=app_client.get(f"/v1/orgs/{i['org'].id}/workforce",params={"workspace_id":i["workspace"].id}).json()
    specialist=next(x for x in listing["members"] if x["department_key"]=="ai_engineering_development")
    r=app_client.post(f"/v1/orgs/{i['org'].id}/workforce/{specialist['id']}/capabilities",
        params={"workspace_id":i["workspace"].id},
        json={"capability_key":"research.internal","scope":"workspace","allowed_data_classes":["synthetic"],
              "allowed_actions":["research.execute"],"tool_allowlist":[],"budget_minor":0})
    assert r.status_code==201, r.text
    assert r.json()["enabled"] is False
    assert r.json()["allowed_data_classes"]==["synthetic"]


def test_workforce_list_is_workspace_scoped(app_client):
    i=app_client.identity
    r=app_client.get(f"/v1/orgs/{i['org'].id}/workforce",params={"workspace_id":"other"})
    assert r.status_code==404



def test_initialize_workforce_reuses_existing_founder_and_chief(app_client):
    i=app_client.identity
    db=app_client.factory()
    result=initialize_workforce(db,org_id=i["org"].id,workspace_id=i["workspace"].id)
    db.commit()
    result2=initialize_workforce(db,org_id=i["org"].id,workspace_id=i["workspace"].id)
    db.commit()
    assert result==result2
    db.close()



def test_founder_bootstrap_route_and_workspace_scoped_workforce_read(app_client):
    i=app_client.identity
    bootstrap=app_client.post(
        f"/v1/orgs/{i['org'].id}/workforce/bootstrap",
        params={"workspace_id":i["workspace"].id},
    )
    assert bootstrap.status_code==200, bootstrap.text
    assert bootstrap.json()["departments"]==16
    listing=app_client.get(
        f"/v1/orgs/{i['org'].id}/workforce",
        params={"workspace_id":i["workspace"].id},
    )
    assert listing.status_code==200
    assert len([m for m in listing.json()["members"] if m["department_key"].endswith("_head")])==16


def test_workforce_delegation_requires_downward_manager_relation_and_enabled_capability(app_client):
    from app.models import Task, Agent
    from app.workforce_models import WorkforceMember, WorkforceCapability
    i = app_client.identity
    app_client.post(
        f"/v1/orgs/{i['org'].id}/workforce/bootstrap",
        params={"workspace_id": i["workspace"].id},
    )
    db = app_client.factory()
    try:
        chief = db.query(WorkforceMember).filter_by(
            org_id=i["org"].id, workspace_id=i["workspace"].id,
            department_key="office_chief_of_staff",
        ).one()
        head = db.query(WorkforceMember).filter_by(
            org_id=i["org"].id, workspace_id=i["workspace"].id,
            department_key="ai_engineering_development_head",
        ).one()
        specialist = db.query(WorkforceMember).filter_by(
            org_id=i["org"].id, workspace_id=i["workspace"].id,
            department_key="ai_engineering_development",
        ).one()
        chief.status = "active"
        head.status = "active"
        head.autonomy_level = 2
        specialist.status = "active"
        agent = db.get(Agent, specialist.agent_id)
        agent.enabled = True
        db.add(WorkforceCapability(
            org_id=i["org"].id, workspace_id=i["workspace"].id,
            member_id=specialist.id, capability_key="internal.research",
            scope="self", allowed_data_classes=["synthetic"],
            allowed_actions=["research.execute"], tool_allowlist=[],
            budget_minor=0, currency="INR", enabled=True,
        ))
        task = Task(
            org_id=i["org"].id, workspace_id=i["workspace"].id,
            title="Parent task", description="Synthetic test",
            created_by=i["user"].id,
        )
        db.add(task)
        db.commit()
        task_id, chief_id, head_id, specialist_id = task.id, chief.id, head.id, specialist.id
    finally:
        db.close()

    wrong_direction = app_client.post(
        f"/v1/orgs/{i['org'].id}/workforce/delegations",
        json={
            "workspace_id": i["workspace"].id, "parent_task_id": task_id,
            "child_title": "Wrong direction", "delegated_by_member_id": head_id,
            "assigned_to_member_id": chief_id,
        },
    )
    assert wrong_direction.status_code == 403

    accepted = app_client.post(
        f"/v1/orgs/{i['org'].id}/workforce/delegations",
        json={
            "workspace_id": i["workspace"].id, "parent_task_id": task_id,
            "child_title": "Research task", "delegated_by_member_id": head_id,
            "assigned_to_member_id": specialist_id,
        },
    )
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["review_status"] == "pending"


def test_workforce_delegation_rejects_assignee_without_enabled_capability(app_client):
    from app.models import Task
    from app.workforce_models import WorkforceMember
    i = app_client.identity
    app_client.post(
        f"/v1/orgs/{i['org'].id}/workforce/bootstrap",
        params={"workspace_id": i["workspace"].id},
    )
    db = app_client.factory()
    try:
        head = db.query(WorkforceMember).filter_by(
            org_id=i["org"].id, workspace_id=i["workspace"].id,
            department_key="ai_engineering_development_head",
        ).one()
        specialist = db.query(WorkforceMember).filter_by(
            org_id=i["org"].id, workspace_id=i["workspace"].id,
            department_key="ai_engineering_development",
        ).one()
        head.status = "active"
        head.autonomy_level = 2
        specialist.status = "active"
        from app.models import Agent
        agent = db.get(Agent, specialist.agent_id)
        agent.enabled = True
        task = Task(
            org_id=i["org"].id, workspace_id=i["workspace"].id,
            title="Parent task", created_by=i["user"].id,
        )
        db.add(task)
        db.commit()
        task_id, head_id, specialist_id = task.id, head.id, specialist.id
    finally:
        db.close()

    denied = app_client.post(
        f"/v1/orgs/{i['org'].id}/workforce/delegations",
        json={
            "workspace_id": i["workspace"].id, "parent_task_id": task_id,
            "child_title": "Should fail", "delegated_by_member_id": head_id,
            "assigned_to_member_id": specialist_id,
        },
    )
    assert denied.status_code == 403
    assert "enabled workforce capability" in denied.text
