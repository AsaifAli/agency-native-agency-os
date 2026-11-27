import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import Principal, get_principal
from app.db import Base, get_db, set_rls_context
from app.domain_routes import router
from app.models import FounderAuthority, Membership, Organization, Role, User, Workspace, WorkspaceGrant
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
    db.add(WorkspaceGrant(
        org_id=org.id, workspace_id=ws.id, user_id=user.id, granted_by=user.id,
    ))
    foreign_client = Client(
        org_id=other_org.id, workspace_id=other_ws.id,
        name="Foreign client", created_by=user.id,
    )
    db.add(foreign_client)
    db.commit()

    app = FastAPI()
    app.include_router(router)
    principal = {"user": user}

    def override_db():
        session = TestingSession()
        try:
            set_rls_context(session, user_id=principal["user"].id)
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_principal] = lambda: Principal(user=principal["user"])
    test_client = TestClient(app)
    test_client.testing_session_factory = TestingSession
    test_client.set_principal = lambda selected_user: principal.update(user=selected_user)
    test_client.org_id = org.id
    test_client.user_id = user.id
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

    duplicate = client.post(f"/v1/orgs/{org}/contacts", headers=auth(), json={
        "workspace_id": ws, "client_id": client_id,
        "first_name": "Asha Duplicate", "email": "  asha@EXAMPLE.test ",
    })
    assert duplicate.status_code == 409

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


def test_agent_research_and_outreach_drafts_are_source_backed_and_never_send(client):
    org, ws = client.org_id, client.ws_id
    lead = client.post(f"/v1/orgs/{org}/leads", headers=auth(), json={
        "workspace_id": ws, "company_name": "Research Target Ltd",
        "contact_name": "Asha", "email": "asha@example.test",
        "source": "agent_research",
    })
    assert lead.status_code == 201, lead.text
    lead_id = lead.json()["id"]
    research = client.post(f"/v1/orgs/{org}/lead-research", headers=auth(), json={
        "workspace_id": ws, "lead_id": lead_id,
        "summary": "The company is expanding its data platform and has a relevant automation need.",
        "fit_score": 84, "confidence_score": 72,
        "buying_signals": ["Public hiring for data engineering"],
        "risks": ["Budget authority is not confirmed"],
        "source_references": [{
            "label": "Company careers page", "url": "https://example.test/careers",
            "accessed_at": "2026-11-25T10:00:00Z",
        }],
    })
    assert research.status_code == 201, research.text
    research_id = research.json()["id"]
    assert research.json()["source_references"][0]["url"] == "https://example.test/careers"
    cross_workspace_research = client.get(
        f"/v1/orgs/{org}/leads/{lead_id}/research?workspace_id={client.other_ws_id}",
        headers=auth(),
    )
    assert cross_workspace_research.status_code == 404
    other_workspace_drafts = client.get(
        f"/v1/orgs/{org}/outreach-drafts?workspace_id={client.other_ws_id}",
        headers=auth(),
    )
    # A workspace from another organization is not visible through this org route.
    assert other_workspace_drafts.status_code == 404
    future_research = client.post(f"/v1/orgs/{org}/lead-research", headers=auth(), json={
        "workspace_id": ws, "lead_id": lead_id,
        "summary": "Future-dated research evidence must be rejected by the API.",
        "fit_score": 50, "confidence_score": 50,
        "researched_at": "2027-01-01T00:00:00Z",
        "source_references": [{
            "label": "Company careers page", "url": "https://example.test/careers",
            "accessed_at": "2026-11-25T10:00:00Z",
        }],
    })
    assert future_research.status_code == 422

    invalid_source = client.post(f"/v1/orgs/{org}/lead-research", headers=auth(), json={
        "workspace_id": ws, "lead_id": lead_id,
        "summary": "This research uses an unsafe source reference and must be rejected.",
        "fit_score": 50, "confidence_score": 50,
        "source_references": [{
            "label": "Unsafe URL", "url": "http://example.test",
            "accessed_at": "2026-11-25T10:00:00Z",
        }],
    })
    assert invalid_source.status_code == 422

    draft = client.post(f"/v1/orgs/{org}/outreach-drafts", headers=auth(), json={
        "workspace_id": ws, "lead_id": lead_id, "channel": "email",
        "subject": "Thought on your data platform",
        "body": "I noticed your team is expanding its data platform and wanted to share a relevant idea.",
        "personalization_basis": "Company careers page; research record " + research_id,
        "source_research_ids": [research_id],
    })
    assert draft.status_code == 201, draft.text
    draft_id = draft.json()["id"]
    assert draft.json()["status"] == "draft"

    db = client.app.dependency_overrides
    from app.db import get_db
    session_generator = db[get_db]()
    session = next(session_generator)
    try:
        from app.models import FounderAuthority
        session.add(FounderAuthority(
            org_id=org, user_id=client_user_id(client),
            grant_source="test_outreach_review",
        ))
        session.commit()
    finally:
        session_generator.close()

    reviewed = client.post(f"/v1/orgs/{org}/outreach-drafts/{draft_id}/review", headers=auth(), json={
        "decision": "approve_draft", "note": "Draft reviewed; dispatch remains a separate gated action.",
    })
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["status"] == "approved_draft"
    assert "send" not in reviewed.json()


def client_user_id(client):
    from app.db import get_db
    generator = client.app.dependency_overrides[get_db]()
    session = next(generator)
    try:
        from app.models import User
        return session.query(User.id).filter_by(email="domain-owner@example.test").scalar()
    finally:
        generator.close()


def test_contact_activity_timeline_is_scoped_and_append_only(client):
    org, ws = client.org_id, client.ws_id
    created = client.post(f"/v1/orgs/{org}/contacts", headers=auth(), json={
        "workspace_id": ws, "first_name": "Asha", "email": "asha-activity@example.test",
    })
    assert created.status_code == 201, created.text
    contact_id = created.json()["id"]

    activity = client.post(f"/v1/orgs/{org}/contact-activities", headers=auth(), json={
        "workspace_id": ws, "contact_id": contact_id,
        "activity_type": "call", "direction": "inbound",
        "subject": "Discovery call", "body": "Prospect asked about workflow automation.",
        "outcome": "Founder follow-up requested",
    })
    assert activity.status_code == 201, activity.text
    activity_id = activity.json()["id"]

    timeline = client.get(
        f"/v1/orgs/{org}/contacts/{contact_id}/activities",
        headers=auth(), params={"workspace_id": ws},
    )
    assert timeline.status_code == 200, timeline.text
    assert [row["id"] for row in timeline.json()] == [activity_id]
    assert timeline.json()[0]["direction"] == "inbound"

    # A contact from this workspace cannot be read through another workspace scope.
    foreign_scope = client.get(
        f"/v1/orgs/{org}/contacts/{contact_id}/activities",
        headers=auth(), params={"workspace_id": client.other_ws_id},
    )
    assert foreign_scope.status_code == 404

    # There is deliberately no update/delete endpoint for historical interactions.
    changed = client.patch(
        f"/v1/orgs/{org}/contact-activities/{activity_id}",
        headers=auth(), json={"body": "rewritten history"},
    )
    assert changed.status_code == 404



def test_opportunity_can_be_linked_to_workspace_client_only(client):
    org, ws = client.org_id, client.ws_id
    local_client = client.post(
        f"/v1/orgs/{org}/clients", headers=auth(),
        json={"workspace_id": ws, "name": "Contract-ready Client"},
    )
    assert local_client.status_code == 201, local_client.text
    opportunity = client.post(
        f"/v1/orgs/{org}/opportunities", headers=auth(), json={
            "workspace_id": ws, "title": "Contract-ready engagement",
            "amount_minor": 500000, "currency": "INR", "probability": 80,
        },
    )
    assert opportunity.status_code == 201, opportunity.text
    linked = client.patch(
        f"/v1/orgs/{org}/opportunities/{opportunity.json()['id']}",
        headers=auth(), json={"stage": "proposal", "client_id": local_client.json()["id"]},
    )
    assert linked.status_code == 200, linked.text
    assert linked.json()["client_id"] == local_client.json()["id"]

    unlinked = client.patch(
        f"/v1/orgs/{org}/opportunities/{opportunity.json()['id']}",
        headers=auth(), json={"stage": "proposal", "client_id": None},
    )
    assert unlinked.status_code == 200, unlinked.text
    assert unlinked.json()["client_id"] is None

    foreign = client.patch(
        f"/v1/orgs/{org}/opportunities/{opportunity.json()['id']}",
        headers=auth(), json={"stage": "proposal", "client_id": client.foreign_client_id},
    )
    assert foreign.status_code == 404



def test_founder_authority_viewer_can_link_opportunity_to_client(client):
    org, ws = client.org_id, client.ws_id
    client_record = client.post(
        f"/v1/orgs/{org}/clients", headers=auth(),
        json={"workspace_id": ws, "name": "Founder controlled client"},
    )
    assert client_record.status_code == 201
    opportunity = client.post(
        f"/v1/orgs/{org}/opportunities", headers=auth(), json={
            "workspace_id": ws, "title": "Founder controlled opportunity",
            "amount_minor": 100000, "currency": "INR", "probability": 40,
        },
    )
    assert opportunity.status_code == 201
    db = client.app.dependency_overrides[get_db]()
    session = next(db)
    try:
        founder_viewer = User(email="founder-domain-viewer@example.test", display_name="Founder Viewer", active=True)
        session.add(founder_viewer)
        session.flush()
        session.add(Membership(org_id=org, user_id=founder_viewer.id, role=Role.viewer))
        session.add(FounderAuthority(org_id=org, user_id=founder_viewer.id, active=True, grant_source="test"))
        session.add(WorkspaceGrant(
            org_id=org, workspace_id=ws, user_id=founder_viewer.id, granted_by=client.user_id,
        ))
        session.flush()
        from app.auth import has_founder_authority
        assert founder_viewer.active is True
        assert session.query(Membership).filter_by(
            org_id=org, user_id=founder_viewer.id
        ).one_or_none() is not None
        assert session.query(FounderAuthority).filter_by(
            org_id=org, user_id=founder_viewer.id, active=True
        ).one_or_none() is not None
        # Commit the grant fixture before opening a separate request session.
        session.commit()
        verify_session = client.testing_session_factory()
        try:
            persisted_user = verify_session.query(User).filter_by(
                id=founder_viewer.id, active=True
            ).one_or_none()
            assert persisted_user is not None, "Founder-viewer user row was not persisted"
            assert has_founder_authority(verify_session, org, founder_viewer.id), (
                "Founder authority must be effective only for a persisted active user "
                "with active membership and an active founder grant"
            )
        finally:
            verify_session.close()
        client.set_principal(founder_viewer)
    finally:
        try:
            next(db)
        except StopIteration:
            pass
    linked = client.patch(
        f"/v1/orgs/{org}/opportunities/{opportunity.json()['id']}",
        headers=auth(), json={"stage": "proposal", "client_id": client_record.json()["id"]},
    )
    assert linked.status_code == 200, linked.text
    assert linked.json()["client_id"] == client_record.json()["id"]


def test_cross_workspace_parent_reference_is_rejected(client):
    org, ws, other_ws = client.org_id, client.ws_id, client.other_ws_id
    # A real client in another organization/workspace must not be attachable.
    r = client.post(f"/v1/orgs/{org}/contacts", headers=auth(), json={
        "workspace_id": ws, "client_id": client.foreign_client_id,
        "first_name": "Nope"
    })
    assert r.status_code == 404


def test_project_outcomes_track_targets_measurements_and_founder_acceptance(client):
    org, ws = client.org_id, client.ws_id
    project = client.post(f"/v1/orgs/{org}/projects", headers=auth(), json={
        "workspace_id": ws, "name": "Invoice processing automation",
    })
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]

    outcome = client.post(f"/v1/orgs/{org}/projects/{project_id}/outcomes", headers=auth(), json={
        "workspace_id": ws,
        "title": "Reduce invoice processing time",
        "problem_statement": "Manual invoice processing takes too long.",
        "desired_outcome": "Reduce average processing time from 10 minutes to 4 minutes.",
        "metric_name": "Average invoice processing time",
        "metric_unit": "minutes",
        "direction": "decrease",
        "baseline_value": "10",
        "target_value": "4",
        "measurement_method": "Compare the average processing duration over a representative 30-day period.",
        "acceptance_criteria": [
            "The deployed workflow processes the agreed invoice types.",
            "The workflow meets the agreed QA and security checks.",
        ],
    })
    assert outcome.status_code == 201, outcome.text
    outcome_id = outcome.json()["id"]
    assert outcome.json()["impact_status"] == "not_measured"
    assert outcome.json()["delivery_acceptance_status"] == "pending"

    measurement = client.post(
        f"/v1/orgs/{org}/outcomes/{outcome_id}/measurements",
        headers=auth(), json={
            "workspace_id": ws,
            "value": "3.5",
            "source_type": "client_reported",
            "source_reference": "Client operations report 2026-11",
            "evidence_summary": "Client reported the 30-day average after rollout.",
        },
    )
    assert measurement.status_code == 201, measurement.text
    assert measurement.json()["value"] == "3.500000" or float(measurement.json()["value"]) == 3.5

    listed = client.get(
        f"/v1/orgs/{org}/projects/{project_id}/outcomes",
        headers=auth(), params={"workspace_id": ws},
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["impact_status"] == "target_met"
    assert listed.json()[0]["latest_value"] == "3.500000" or float(listed.json()[0]["latest_value"]) == 3.5
    assert listed.json()[0]["measurement_count"] == 1

    denied = client.post(
        f"/v1/orgs/{org}/outcomes/{outcome_id}/acceptance",
        headers=auth(), json={
            "workspace_id": ws, "decision": "accepted",
            "criteria_results": {
                "The deployed workflow processes the agreed invoice types.": True,
                "The workflow meets the agreed QA and security checks.": True,
            },
            "note": "All delivery acceptance checks were reviewed.",
        },
    )
    assert denied.status_code == 403

    from app.db import get_db
    from app.models import FounderAuthority
    generator = client.app.dependency_overrides[get_db]()
    session = next(generator)
    try:
        session.add(FounderAuthority(
            org_id=org, user_id=client.user_id, grant_source="test_outcome_acceptance",
        ))
        session.commit()
    finally:
        generator.close()

    accepted = client.post(
        f"/v1/orgs/{org}/outcomes/{outcome_id}/acceptance",
        headers=auth(), json={
            "workspace_id": ws, "decision": "accepted",
            "criteria_results": {
                "The deployed workflow processes the agreed invoice types.": True,
                "The workflow meets the agreed QA and security checks.": True,
            },
            "note": "All delivery acceptance checks were reviewed.",
        },
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["delivery_acceptance_status"] == "accepted"
    assert accepted.json()["impact_status"] == "target_met"

    # An accepted delivery can still miss its later business-impact target.
    later = client.post(
        f"/v1/orgs/{org}/outcomes/{outcome_id}/measurements",
        headers=auth(), json={
            "workspace_id": ws, "value": "7",
            "source_type": "client_reported",
            "source_reference": "Client operations report 2026-12",
            "evidence_summary": "Follow-up measurement after process volume increased.",
        },
    )
    assert later.status_code == 201, later.text
    refreshed = client.get(
        f"/v1/orgs/{org}/projects/{project_id}/outcomes",
        headers=auth(), params={"workspace_id": ws},
    )
    assert refreshed.status_code == 200
    assert refreshed.json()[0]["delivery_acceptance_status"] == "accepted"
    assert refreshed.json()[0]["impact_status"] == "target_missed"



def test_project_outcome_text_is_sanitized_and_measurements_are_append_only(client):
    org, ws = client.org_id, client.ws_id
    project = client.post(f"/v1/orgs/{org}/projects", headers=auth(), json={
        "workspace_id": ws, "name": "Outcome privacy project",
    })
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]

    unsafe_secret = client.post(
        f"/v1/orgs/{org}/projects/{project_id}/outcomes", headers=auth(), json={
            "workspace_id": ws, "title": "Secret-bearing outcome",
            "problem_statement": "The API key is sk-ant-abcdefghijklmnop and must be rejected.",
            "desired_outcome": "Keep credentials out of persisted outcome records.",
            "metric_name": "Credential exposure", "metric_unit": "count",
            "direction": "decrease", "target_value": "0",
            "measurement_method": "Count detected credential exposures.",
            "acceptance_criteria": ["No credentials are persisted."],
        },
    )
    assert unsafe_secret.status_code == 422

    created = client.post(
        f"/v1/orgs/{org}/projects/{project_id}/outcomes", headers=auth(), json={
            "workspace_id": ws, "title": "Reduce processing time",
            "problem_statement": "Client contact person is a.person@example.test.",
            "desired_outcome": "Reduce average processing time to four minutes.",
            "metric_name": "Processing time", "metric_unit": "minutes",
            "direction": "decrease", "target_value": "4",
            "measurement_method": "Measure the average over a representative month.",
            "acceptance_criteria": ["The agreed workflow passes QA."],
        },
    )
    assert created.status_code == 201, created.text
    assert "a.person@example.test" not in created.json()["problem_statement"]
    assert "[REDACTED_EMAIL]" in created.json()["problem_statement"]

    outcome_id = created.json()["id"]
    measurement = client.post(
        f"/v1/orgs/{org}/outcomes/{outcome_id}/measurements", headers=auth(), json={
            "workspace_id": ws, "value": "3.8", "source_type": "client_reported",
            "source_reference": "Client report 2026-11",
            "evidence_summary": "The client reported the average processing time.",
        },
    )
    assert measurement.status_code == 201, measurement.text
    changed = client.patch(
        f"/v1/orgs/{org}/outcomes/{outcome_id}/measurements/{measurement.json()['id']}",
        headers=auth(), json={"value": "1"},
    )
    assert changed.status_code in {404, 405}



def test_project_outcome_rejects_cross_workspace_parent_and_mismatched_acceptance_criteria(client):
    org, ws = client.org_id, client.ws_id
    project = client.post(f"/v1/orgs/{org}/projects", headers=auth(), json={
        "workspace_id": ws, "name": "Scoped outcome project",
    })
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]

    cross_scope = client.post(
        f"/v1/orgs/{org}/projects/{project_id}/outcomes",
        headers=auth(), json={
            "workspace_id": client.other_ws_id,
            "title": "Cross-workspace outcome",
            "problem_statement": "Scope must be enforced.",
            "desired_outcome": "No cross-workspace records.",
            "metric_name": "Records",
            "metric_unit": "count",
            "direction": "increase",
            "target_value": "1",
            "measurement_method": "Count records.",
            "acceptance_criteria": ["Record is workspace scoped."],
        },
    )
    assert cross_scope.status_code == 404

    created = client.post(
        f"/v1/orgs/{org}/projects/{project_id}/outcomes",
        headers=auth(), json={
            "workspace_id": ws,
            "title": "Scoped outcome",
            "problem_statement": "Scope must be enforced.",
            "desired_outcome": "One verified result.",
            "metric_name": "Records",
            "metric_unit": "count",
            "direction": "increase",
            "target_value": "1",
            "measurement_method": "Count records.",
            "acceptance_criteria": ["Record is workspace scoped."],
        },
    )
    assert created.status_code == 201, created.text
    outcome_id = created.json()["id"]
    from app.db import get_db
    from app.models import FounderAuthority
    generator = client.app.dependency_overrides[get_db]()
    session = next(generator)
    try:
        session.add(FounderAuthority(
            org_id=org, user_id=client.user_id, grant_source="test_outcome_criteria",
        ))
        session.commit()
    finally:
        generator.close()
    cross_workspace_measurement = client.post(
        f"/v1/orgs/{org}/outcomes/{outcome_id}/measurements",
        headers=auth(), json={
            "workspace_id": client.other_ws_id, "value": "1",
            "source_type": "client_reported", "source_reference": "Foreign report",
            "evidence_summary": "A cross-workspace measurement must be rejected.",
        },
    )
    assert cross_workspace_measurement.status_code == 404
    mismatch = client.post(
        f"/v1/orgs/{org}/outcomes/{outcome_id}/acceptance",
        headers=auth(), json={
            "workspace_id": ws, "decision": "accepted",
            "criteria_results": {"A different criterion": True},
            "note": "This must not silently accept an unknown criterion.",
        },
    )
    assert mismatch.status_code == 403
