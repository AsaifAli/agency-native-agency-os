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
    assert r.json()["group_heads"]==5
    assert r.json()["teams"] >= 20
    assert r.json()["positions"] >= 80
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
        "office_executive_assistant","growth","strategy_commercial","technology",
        "delivery_quality","business_operations",
    ])
    assert len(listing.json()["positions"]) >= 80
    assert len([u for u in listing.json()["units"] if u["unit_type"] == "team"]) >= 20


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
        db.get(Agent, head.agent_id).enabled = True
        db.get(Agent, head.agent_id).enabled = True
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
    from app.models import Task, Agent
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
        db.get(Agent, head.agent_id).enabled = True
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
    assert "enabled, data-eligible execution capability" in denied.text


def test_founder_can_enable_capability_activate_execute_and_pause_member(app_client, monkeypatch):
    from app.config import settings
    from app.execution_service import create_execution
    from app.models import Agent, DataClass, Task
    from app.workforce_models import WorkforceMember, WorkforceCapability

    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(settings, "mock_runtime_enabled", True)
    i = app_client.identity
    boot = app_client.post(
        f"/v1/orgs/{i['org'].id}/workforce/bootstrap",
        params={"workspace_id": i["workspace"].id},
    )
    assert boot.status_code == 200, boot.text

    db = app_client.factory()
    try:
        member = db.query(WorkforceMember).filter_by(
            org_id=i["org"].id, workspace_id=i["workspace"].id,
            department_key="ai_engineering_development",
        ).one()
        agent = db.get(Agent, member.agent_id)
        agent.runtime = "mock"
        agent.data_class = DataClass.synthetic
        task = Task(
            org_id=i["org"].id, workspace_id=i["workspace"].id,
            title="Execute internal research", description="Synthetic-only",
            created_by=i["user"].id,
        )
        db.add(task)
        db.commit()
        member_id, agent_id, task_id = member.id, agent.id, task.id
    finally:
        db.close()

    created = app_client.post(
        f"/v1/orgs/{i['org'].id}/workforce/{member_id}/capabilities",
        params={"workspace_id": i["workspace"].id},
        json={
            "capability_key": "research.internal",
            "scope": "self",
            "allowed_data_classes": ["synthetic"],
            "allowed_actions": ["research.execute", "task.execute"],
            "tool_allowlist": [],
            "budget_minor": 0,
            "currency": "INR",
        },
    )
    assert created.status_code == 201, created.text
    capability_id = created.json()["id"]
    assert created.json()["enabled"] is False

    enabled = app_client.post(
        f"/v1/orgs/{i['org'].id}/workforce/{member_id}/capabilities/{capability_id}/enable",
        params={"workspace_id": i["workspace"].id},
    )
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["enabled"] is True

    activated = app_client.post(
        f"/v1/orgs/{i['org'].id}/workforce/{member_id}/activate",
        params={"workspace_id": i["workspace"].id},
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "active"
    assert activated.json()["enabled"] is True

    db = app_client.factory()
    try:
        execution = create_execution(
            db, org_id=i["org"].id, workspace_id=i["workspace"].id,
            task_id=task_id, agent_id=agent_id, requested_by=i["user"].id,
            idempotency_key="workforce-active-member-execution",
        )
        db.commit()
        assert execution.status.value == "queued"
    finally:
        db.close()

    paused = app_client.post(
        f"/v1/orgs/{i['org'].id}/workforce/{member_id}/pause",
        params={"workspace_id": i["workspace"].id},
    )
    assert paused.status_code == 200, paused.text
    assert paused.json()["status"] == "paused"
    db = app_client.factory()
    try:
        member = db.query(WorkforceMember).filter_by(id=member_id).one()
        agent = db.get(Agent, agent_id)
        grant = db.query(WorkforceCapability).filter_by(id=capability_id).one()
        assert member.status == "paused"
        assert agent.enabled is False
        assert grant.enabled is False
    finally:
        db.close()


def test_founder_capability_enable_rejects_protected_or_unknown_actions(app_client):
    from app.workforce_models import WorkforceMember
    i = app_client.identity
    app_client.post(
        f"/v1/orgs/{i['org'].id}/workforce/bootstrap",
        params={"workspace_id": i["workspace"].id},
    )
    db = app_client.factory()
    try:
        member = db.query(WorkforceMember).filter_by(
            org_id=i["org"].id, workspace_id=i["workspace"].id,
            department_key="ai_engineering_development",
        ).one()
        member_id = member.id
    finally:
        db.close()
    created = app_client.post(
        f"/v1/orgs/{i['org'].id}/workforce/{member_id}/capabilities",
        params={"workspace_id": i["workspace"].id},
        json={
            "capability_key": "invalid.protected",
            "allowed_data_classes": ["synthetic"],
            "allowed_actions": ["production.release"],
            "tool_allowlist": [],
        },
    )
    assert created.status_code == 201
    enabled = app_client.post(
        f"/v1/orgs/{i['org'].id}/workforce/{member_id}/capabilities/{created.json()['id']}/enable",
        params={"workspace_id": i["workspace"].id},
    )
    assert enabled.status_code == 403



def test_chief_of_staff_plan_creates_persisted_dependency_graph(app_client):
    from app.workforce_models import WorkforceMember, WorkforceCapability, OrchestrationPlan, Delegation, OrchestrationPlanDelegation
    from app.models import Agent, Task

    i = app_client.identity
    boot = app_client.post(
        f"/v1/orgs/{i['org'].id}/workforce/bootstrap",
        params={"workspace_id": i["workspace"].id},
    )
    assert boot.status_code == 200, boot.text
    db = app_client.factory()
    try:
        chief = db.query(WorkforceMember).filter_by(
            org_id=i["org"].id, workspace_id=i["workspace"].id,
            department_key="office_chief_of_staff",
        ).one()
        chief.status = "active"
        chief.autonomy_level = 2
        db.get(Agent, chief.agent_id).enabled = True
        group_head = db.query(WorkforceMember).filter_by(
            org_id=i["org"].id, workspace_id=i["workspace"].id,
            department_key="technology",
        ).one()
        group_head.status = "active"
        group_head.autonomy_level = 2
        db.get(Agent, group_head.agent_id).enabled = True
        head = db.query(WorkforceMember).filter_by(
            org_id=i["org"].id, workspace_id=i["workspace"].id,
            department_key="ai_engineering_development_head",
        ).one()
        head.status = "active"
        head.autonomy_level = 2
        db.get(Agent, head.agent_id).enabled = True
        specialist = db.query(WorkforceMember).filter_by(
            org_id=i["org"].id, workspace_id=i["workspace"].id,
            department_key="ai_engineering_development",
        ).one()
        specialist.status = "active"
        db.get(Agent, specialist.agent_id).enabled = True
        for member in (group_head, head, specialist):
            db.add(WorkforceCapability(
                org_id=i["org"].id, workspace_id=i["workspace"].id,
                member_id=member.id, capability_key="internal.research",
                scope="self", allowed_data_classes=["synthetic"],
                allowed_actions=["research.execute"], tool_allowlist=[],
                budget_minor=0, currency="INR", enabled=True,
            ))
        db.commit()
        chief_id, group_head_id, head_id, specialist_id = (
            chief.id, group_head.id, head.id, specialist.id
        )
    finally:
        db.close()

    response = app_client.post(
        f"/v1/orgs/{i['org'].id}/workforce/plans",
        json={
            "workspace_id": i["workspace"].id,
            "objective": "Complete a synthetic QA review plan",
            "created_by_member_id": chief_id,
            "plan_title": "Synthetic QA plan",
            "tasks": [
                {
                    "workspace_id": i["workspace"].id,
                    "parent_task_id": "server-binds-root",
                    "child_title": "Prepare QA data",
                    "delegated_by_member_id": chief_id,
                    "assigned_to_member_id": group_head_id,
                    "review_required": False,
                },
                {
                    "workspace_id": i["workspace"].id,
                    "parent_task_id": "server-binds-root",
                    "child_title": "Run QA review",
                    "delegated_by_member_id": head_id,
                    "assigned_to_member_id": specialist_id,
                    "depends_on_ordinal": 1,
                    "review_required": True,
                },
            ],
        },
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["task_count"] == 2
    assert result["blocked_count"] == 1
    assert result["status"] == "in_progress"

    details = app_client.get(
        f"/v1/orgs/{i['org'].id}/workforce/plans/{result['id']}",
        params={"workspace_id": i["workspace"].id},
    )
    assert details.status_code == 200, details.text
    assert len(details.json()["tasks"]) == 2
    assert {task["status"] for task in details.json()["tasks"]} == {"ready", "blocked"}

    db = app_client.factory()
    try:
        plan = db.get(OrchestrationPlan, result["id"])
        links = db.query(OrchestrationPlanDelegation).filter_by(plan_id=plan.id).all()
        rows = [db.get(Delegation, link.delegation_id) for link in links]
        assert len(rows) == 2
        assert all(row.parent_task_id == plan.root_task_id for row in rows)
        assert sorted(row.sequence_no for row in rows) == [1, 2]
        chief = db.query(WorkforceMember).filter_by(id=chief_id).one()
        group_head = db.query(WorkforceMember).filter_by(id=group_head_id).one()
        head = db.query(WorkforceMember).filter_by(id=head_id).one()
        specialist = db.query(WorkforceMember).filter_by(id=specialist_id).one()
        assert group_head.manager_member_id == chief.id
        assert head.manager_member_id == group_head.id
        assert specialist.manager_member_id == head.id
    finally:
        db.close()

    cycle = app_client.post(
        f"/v1/orgs/{i['org'].id}/workforce/plans",
        json={
            "workspace_id": i["workspace"].id,
            "objective": "Reject a cyclic plan dependency",
            "created_by_member_id": chief_id,
            "tasks": [
                {
                    "workspace_id": i["workspace"].id,
                    "parent_task_id": "server-binds-root",
                    "child_title": "Task one",
                    "delegated_by_member_id": chief_id,
                    "assigned_to_member_id": group_head_id,
                    "depends_on_ordinal": 2,
                },
                {
                    "workspace_id": i["workspace"].id,
                    "parent_task_id": "server-binds-root",
                    "child_title": "Task two",
                    "delegated_by_member_id": head_id,
                    "assigned_to_member_id": specialist_id,
                },
            ],
        },
    )
    assert cycle.status_code == 422, cycle.text

    # Review cannot be passed before the delegated work reaches a terminal state.
    first_delegation_id = details.json()["tasks"][0]["delegation_id"]
    early_review = app_client.post(
        f"/v1/orgs/{i['org'].id}/workforce/delegations/{first_delegation_id}/review",
        params={"workspace_id": i["workspace"].id, "decision": "waived"},
    )
    assert early_review.status_code == 409

    db = app_client.factory()
    try:
        blocked_row = db.get(Delegation, first_delegation_id)
        blocked_task = db.get(Task, blocked_row.child_task_id)
        blocked_row.status = "blocked"
        blocked_row.last_error_code = "AgentNotEnabled"
        blocked_task.status = "blocked"
        db.commit()
    finally:
        db.close()
    requeued = app_client.post(
        f"/v1/orgs/{i['org'].id}/workforce/delegations/{first_delegation_id}/requeue",
        params={"workspace_id": i["workspace"].id},
    )
    assert requeued.status_code == 200, requeued.text
    assert requeued.json()["status"] == "ready"


def test_non_supervisor_cannot_create_plan(app_client):
    from app.workforce_models import WorkforceMember
    i = app_client.identity
    app_client.post(
        f"/v1/orgs/{i['org'].id}/workforce/bootstrap",
        params={"workspace_id": i["workspace"].id},
    )
    db = app_client.factory()
    try:
        specialist = db.query(WorkforceMember).filter_by(
            org_id=i["org"].id, workspace_id=i["workspace"].id,
            department_key="ai_engineering_development",
        ).one()
        specialist.status = "active"
        db.commit()
        specialist_id = specialist.id
    finally:
        db.close()
    response = app_client.post(
        f"/v1/orgs/{i['org'].id}/workforce/plans",
        json={
            "workspace_id": i["workspace"].id,
            "objective": "Prepare an approved work plan",
            "created_by_member_id": specialist_id,
            "tasks": [{
                "workspace_id": i["workspace"].id,
                "parent_task_id": "ignored",
                "child_title": "Should not be assigned",
                "delegated_by_member_id": specialist_id,
                "assigned_to_member_id": specialist_id,
            }],
        },
    )
    assert response.status_code == 403


def test_plan_read_api_rejects_other_workspace(app_client):
    i = app_client.identity
    response = app_client.get(
        f"/v1/orgs/{i['org'].id}/workforce/plans",
        params={"workspace_id": "other-workspace"},
    )
    assert response.status_code == 404


def test_supervisor_plan_cannot_delegate_outside_its_reporting_tree(app_client):
    from app.workforce_models import WorkforceMember, WorkforceCapability
    from app.models import Agent

    i = app_client.identity
    boot = app_client.post(
        f"/v1/orgs/{i['org'].id}/workforce/bootstrap",
        params={"workspace_id": i["workspace"].id},
    )
    assert boot.status_code == 200, boot.text
    db = app_client.factory()
    try:
        technology = db.query(WorkforceMember).filter_by(
            org_id=i["org"].id, workspace_id=i["workspace"].id,
            department_key="technology",
        ).one()
        growth = db.query(WorkforceMember).filter_by(
            org_id=i["org"].id, workspace_id=i["workspace"].id,
            department_key="growth",
        ).one()
        marketing_head = db.query(WorkforceMember).filter_by(
            org_id=i["org"].id, workspace_id=i["workspace"].id,
            department_key="marketing_brand_head",
        ).one()
        for member in (technology, growth, marketing_head):
            member.status = "active"
            member.autonomy_level = 2
            db.get(Agent, member.agent_id).enabled = True
        db.add(WorkforceCapability(
            org_id=i["org"].id, workspace_id=i["workspace"].id,
            member_id=marketing_head.id, capability_key="internal.research",
            scope="self", allowed_data_classes=["synthetic"],
            allowed_actions=["research.execute"], tool_allowlist=[],
            budget_minor=0, currency="INR", enabled=True,
        ))
        assert growth.manager_member_id != technology.id
        assert marketing_head.manager_member_id == growth.id
        technology_id, growth_id, marketing_head_id = (
            technology.id, growth.id, marketing_head.id
        )
        db.commit()
    finally:
        db.close()

    response = app_client.post(
        f"/v1/orgs/{i['org'].id}/workforce/plans",
        json={
            "workspace_id": i["workspace"].id,
            "objective": "Reject delegation outside this supervisor's authority",
            "created_by_member_id": technology_id,
            "tasks": [{
                "workspace_id": i["workspace"].id,
                "parent_task_id": "server-owned-root",
                "child_title": "Marketing research task",
                "delegated_by_member_id": growth_id,
                "assigned_to_member_id": marketing_head_id,
            }],
        },
    )
    assert response.status_code == 403
    assert "outside the plan creator's reporting tree" in response.text


def test_non_founder_cannot_refresh_orchestration_plan(app_client):
    i = app_client.identity
    app_client.app.dependency_overrides[get_principal] = (
        lambda: Principal(user=i["operator"])
    )
    response = app_client.post(
        f"/v1/orgs/{i['org'].id}/workforce/plans/not-a-plan/refresh",
        params={"workspace_id": i["workspace"].id},
    )
    assert response.status_code == 403



def test_skill_catalog_api_is_authenticated_and_tool_free(app_client):
    identity = app_client.identity
    response = app_client.get(f"/v1/orgs/{identity['org'].id}/skills")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload["skills"]) == 10
    assert all(skill["enabled"] is False for skill in payload["skills"])
    assert all(skill["allowed_tools"] == [] for skill in payload["skills"])

    detail = app_client.get(
        f"/v1/orgs/{identity['org'].id}/skills/test-driven-development"
    )
    assert detail.status_code == 200, detail.text
    assert "red-green-refactor" in detail.json()["content"]
    assert detail.json()["sources"]

    missing = app_client.get(
        f"/v1/orgs/{identity['org'].id}/skills/not-a-real-skill"
    )
    assert missing.status_code == 404
