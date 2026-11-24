import pytest
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import Principal, get_principal
from app.db import Base, get_db
from app.models import (
    Approval, ApprovalStatus, FounderAuthority, Membership, Organization,
    Role, User, Workspace, Task,
)
from app.domain_models import Project, Opportunity, Client
from app.operations_models import ServicePlaybook, ServiceOffering, Proposal, ContractRecord, ClientOnboarding, OnboardingChecklistItem, InvoiceRecord, PaymentReceipt, ScopeChangeRequest, TimeEntry, ProjectCost
from app.operations_routes import router
from app.telephony.models import OutboxEvent


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    db = TestingSession()
    user = User(email="founder-ops@example.test", display_name="Founder")
    org = Organization(name="Operations Test Org")
    other_org = Organization(name="Other Org")
    db.add_all([user, org, other_org])
    db.flush()
    ws = Workspace(id="ops-ws", org_id=org.id, name="Workspace")
    other_ws = Workspace(id="ops-other-ws", org_id=other_org.id, name="Other")
    db.add_all([ws, other_ws])
    db.add_all([
        Membership(org_id=org.id, user_id=user.id, role=Role.owner),
        FounderAuthority(org_id=org.id, user_id=user.id, grant_source="test"),
    ])
    client = Client(
        org_id=org.id, workspace_id=ws.id, name="Acme Test Client",
        created_by=user.id,
    )
    db.add(client)
    db.flush()
    project = Project(
        org_id=org.id, workspace_id=ws.id, name="Build AI workflow",
        client_id=client.id,
        budget_minor=500000, contract_value_minor=1200000,
        estimated_hours=80, currency="INR", owner_user_id=user.id,
        due_date=datetime(2027, 1, 31, tzinfo=timezone.utc),
    )
    db.add(project)
    db.flush()
    opportunity = Opportunity(
        org_id=org.id, workspace_id=ws.id, client_id=client.id, title="AI workflow engagement",
        amount_minor=1500000, currency="INR", probability=60, owner_user_id=user.id,
    )
    db.add(opportunity)
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
    tc = TestClient(app)
    tc.org_id, tc.ws_id, tc.other_ws_id, tc.user_id, tc.project_id, tc.opportunity_id, tc.client_id = org.id, ws.id, other_ws.id, user.id, project.id, opportunity.id, client.id
    tc.session_factory = TestingSession
    yield tc
    db.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def headers():
    return {"Authorization": "Bearer test"}


def test_playbook_create_and_founder_activation(client):
    org, ws = client.org_id, client.ws_id
    created = client.post(f"/v1/orgs/{org}/operations/playbooks", headers=headers(), json={
        "workspace_id": ws, "title": "Enterprise RAG delivery",
        "service_line": "custom_ai_applications",
        "required_inputs": ["sample documents", "identity requirements"],
        "deliverables": ["retrieval API", "evaluation report"],
        "acceptance_criteria": ["citations verified", "tenant isolation tested"],
        "security_checks": ["PII review", "access control tests"],
    })
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "draft"
    activated = client.patch(
        f"/v1/orgs/{org}/operations/playbooks/{created.json()['id']}/status",
        headers=headers(), json={"status": "active"},
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["version"] == 2


def test_proposal_supports_one_time_and_retainer_engagement_terms(client):
    org, ws = client.org_id, client.ws_id
    base = {
        "workspace_id": ws, "opportunity_id": client.opportunity_id,
        "title": "Managed AI operations retainer", "service_line": "AI Engineering",
        "scope_summary": "Ongoing operation, monitoring and improvement of the agreed AI workflows.",
        "amount_minor": 950000, "currency": "INR",
    }
    invalid = client.post(f"/v1/orgs/{org}/operations/proposals", headers=headers(), json={
        **base, "engagement_type": "retainer", "billing_frequency": "one_time",
        "term_months": 6, "included_hours_per_period": 40,
    })
    assert invalid.status_code == 422
    created = client.post(f"/v1/orgs/{org}/operations/proposals", headers=headers(), json={
        **base, "engagement_type": "retainer", "billing_frequency": "monthly",
        "term_months": 6, "included_hours_per_period": 40,
        "rollover_hours": True, "support_response_hours": 8,
        "auto_renew": False,
    })
    assert created.status_code == 201, created.text
    payload = created.json()
    assert payload["engagement_type"] == "retainer"
    assert payload["billing_frequency"] == "monthly"
    assert payload["term_months"] == 6
    assert payload["included_hours_per_period"] == 40
    assert payload["rollover_hours"] is True
    assert payload["support_response_hours"] == 8
    assert payload["auto_renew"] is False
    one_time = client.post(f"/v1/orgs/{org}/operations/proposals", headers=headers(), json={
        **base, "title": "One-time AI implementation",
    })
    assert one_time.status_code == 201, one_time.text
    assert one_time.json()["engagement_type"] == "one_time"
    assert one_time.json()["billing_frequency"] == "one_time"


def test_proposal_requires_single_use_founder_pricing_approval(client):
    org, ws, opportunity = client.org_id, client.ws_id, client.opportunity_id
    created = client.post(f"/v1/orgs/{org}/operations/proposals", headers=headers(), json={
        "workspace_id": ws, "opportunity_id": opportunity,
        "title": "AI workflow implementation proposal", "service_line": "AI Engineering",
        "scope_summary": "Design, implement and evaluate an internal workflow automation system.",
        "deliverables": ["Workflow API", "Evaluation report"],
        "assumptions": ["Client provides source access"],
        "exclusions": ["Third-party subscription fees"],
        "amount_minor": 1800000, "currency": "INR", "validity_days": 30,
    })
    assert created.status_code == 201, created.text
    proposal_id = created.json()["id"]
    assert created.json()["status"] == "draft"

    submitted = client.post(
        f"/v1/orgs/{org}/operations/proposals/{proposal_id}/submit-for-approval",
        headers=headers(),
    )
    assert submitted.status_code == 200, submitted.text
    approval_id = submitted.json()["approval_id"]
    assert submitted.json()["status"] == "pending_approval"

    premature = client.post(
        f"/v1/orgs/{org}/operations/proposals/{proposal_id}/approve",
        headers=headers(), json={"approval_id": approval_id},
    )
    assert premature.status_code == 409

    db = client.session_factory()
    try:
        approval = db.query(Approval).filter_by(id=approval_id).one()
        approval.status = ApprovalStatus.approved
        approval.decided_by = client.user_id
        approval.decided_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()

    approved = client.post(
        f"/v1/orgs/{org}/operations/proposals/{proposal_id}/approve",
        headers=headers(), json={"approval_id": approval_id},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"

    repeated = client.post(
        f"/v1/orgs/{org}/operations/proposals/{proposal_id}/approve",
        headers=headers(), json={"approval_id": approval_id},
    )
    assert repeated.status_code == 409

    db = client.session_factory()
    try:
        approval = db.query(Approval).filter_by(id=approval_id).one()
        assert approval.consumed_at is not None
        assert approval.consumed_by == client.user_id
    finally:
        db.close()


def test_founder_can_reject_proposal_and_approval_together(client):
    org, ws = client.org_id, client.ws_id
    created = client.post(f"/v1/orgs/{org}/operations/proposals", headers=headers(), json={
        "workspace_id": ws, "opportunity_id": client.opportunity_id,
        "title": "Alternative engagement proposal", "service_line": "AI Engineering",
        "scope_summary": "A scoped discovery and implementation engagement for internal automation.",
        "amount_minor": 100000, "currency": "INR",
    })
    assert created.status_code == 201, created.text
    proposal_id = created.json()["id"]
    submitted = client.post(
        f"/v1/orgs/{org}/operations/proposals/{proposal_id}/submit-for-approval",
        headers=headers(),
    )
    approval_id = submitted.json()["approval_id"]
    rejected = client.post(
        f"/v1/orgs/{org}/operations/proposals/{proposal_id}/reject",
        headers=headers(), json={"approval_id": approval_id, "note": "Commercial scope needs revision"},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"
    db = client.session_factory()
    try:
        approval = db.query(Approval).filter_by(id=approval_id).one()
        assert approval.status == ApprovalStatus.rejected
        assert approval.decided_by == client.user_id
    finally:
        db.close()


def test_proposal_can_sync_an_existing_founder_rejection(client):
    org = client.org_id
    created = client.post(f"/v1/orgs/{org}/operations/proposals", headers=headers(), json={
        "workspace_id": client.ws_id, "opportunity_id": client.opportunity_id,
        "title": "Proposal requiring revision", "service_line": "AI Engineering",
        "scope_summary": "A proposal draft that must be rejected through the approvals queue.",
        "amount_minor": 250000, "currency": "INR",
    })
    assert created.status_code == 201, created.text
    proposal_id = created.json()["id"]
    submitted = client.post(
        f"/v1/orgs/{org}/operations/proposals/{proposal_id}/submit-for-approval",
        headers=headers(),
    )
    approval_id = submitted.json()["approval_id"]
    db = client.session_factory()
    try:
        approval = db.query(Approval).filter_by(id=approval_id).one()
        approval.status = ApprovalStatus.rejected
        approval.decided_by = client.user_id
        approval.decision_note = "Rejected in the central approval queue"
        approval.decided_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()
    synced = client.post(
        f"/v1/orgs/{org}/operations/proposals/{proposal_id}/reject",
        headers=headers(), json={"approval_id": approval_id, "note": "Synchronize proposal status"},
    )
    assert synced.status_code == 200, synced.text
    assert synced.json()["status"] == "rejected"


def test_proposal_rejects_cross_workspace_opportunity_and_currency(client):
    org = client.org_id
    payload = {
        "workspace_id": client.ws_id, "opportunity_id": "not-an-opportunity",
        "title": "Invalid proposal", "service_line": "AI Engineering",
        "scope_summary": "This proposal must not attach to an unknown opportunity.",
        "amount_minor": 100000, "currency": "INR",
    }
    missing = client.post(f"/v1/orgs/{org}/operations/proposals", headers=headers(), json=payload)
    assert missing.status_code == 404
    payload["opportunity_id"] = client.opportunity_id
    payload["currency"] = "USD"
    mismatch = client.post(f"/v1/orgs/{org}/operations/proposals", headers=headers(), json=payload)
    assert mismatch.status_code == 422


def test_service_catalogue_draft_requires_founder_activation(client):
    org, ws = client.org_id, client.ws_id
    missing_price = client.post(f"/v1/orgs/{org}/operations/service-catalog", headers=headers(), json={
        "workspace_id": ws, "code": "workflow-build", "name": "Workflow Build",
        "service_line": "AI Engineering", "description": "Design and build a governed workflow automation solution.",
        "pricing_model": "fixed", "currency": "INR",
    })
    assert missing_price.status_code == 422

    created = client.post(f"/v1/orgs/{org}/operations/service-catalog", headers=headers(), json={
        "workspace_id": ws, "code": "workflow-build", "name": "Workflow Build",
        "service_line": "AI Engineering", "description": "Design and build a governed workflow automation solution.",
        "pricing_model": "custom", "currency": "INR", "typical_duration_days": 30,
        "target_outcomes": ["Reduce manual operations"],
        "deliverables": ["Workflow API", "Evaluation report"],
        "required_inputs": ["Process documentation"], "exclusions": ["Provider subscription fees"],
    })
    assert created.status_code == 201, created.text
    offering_id = created.json()["id"]
    assert created.json()["status"] == "draft"

    duplicate = client.post(f"/v1/orgs/{org}/operations/service-catalog", headers=headers(), json={
        "workspace_id": ws, "code": "workflow-build", "name": "Duplicate Offering",
        "service_line": "AI Engineering", "description": "Another duplicate catalogue entry.",
        "pricing_model": "custom", "currency": "INR",
    })
    assert duplicate.status_code == 409

    db = client.session_factory()
    try:
        founder = db.query(User).filter_by(id=client.user_id).one()
        operator = User(email="catalog-operator@example.test", display_name="Operator")
        db.add(operator); db.flush()
        db.add(Membership(org_id=org, user_id=operator.id, role=Role.operator))
        db.commit()
        client.app.dependency_overrides[get_principal] = lambda: Principal(user=operator)
    finally:
        db.close()
    denied = client.patch(
        f"/v1/orgs/{org}/operations/service-catalog/{offering_id}/status",
        headers=headers(), json={"status": "active"},
    )
    assert denied.status_code == 403
    client.app.dependency_overrides[get_principal] = lambda: Principal(user=founder)
    activated = client.patch(
        f"/v1/orgs/{org}/operations/service-catalog/{offering_id}/status",
        headers=headers(), json={"status": "active"},
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "active"
    assert activated.json()["version"] == 1

    retired = client.patch(
        f"/v1/orgs/{org}/operations/service-catalog/{offering_id}/status",
        headers=headers(), json={"status": "retired"},
    )
    assert retired.status_code == 200, retired.text
    revised = client.post(f"/v1/orgs/{org}/operations/service-catalog", headers=headers(), json={
        "workspace_id": ws, "code": "workflow-build", "name": "Workflow Build v2",
        "service_line": "AI Engineering", "description": "Revised workflow automation service offering.",
        "pricing_model": "custom", "currency": "INR",
    })
    assert revised.status_code == 201, revised.text
    assert revised.json()["version"] == 2
    assert revised.json()["status"] == "draft"



def _create_approved_proposal_for_contract(client, engagement_terms=None):
    proposal_payload = {
        "workspace_id": client.ws_id, "opportunity_id": client.opportunity_id,
        "title": "Signed AI workflow engagement", "service_line": "AI Engineering",
        "scope_summary": "Design, implement and evaluate a governed AI workflow for the client.",
        "deliverables": ["Workflow API", "Evaluation report"],
        "assumptions": ["Client provides access"], "exclusions": ["Cloud subscription fees"],
        "amount_minor": 1800000, "currency": "INR", "validity_days": 30,
    }
    proposal_payload.update(engagement_terms or {})
    response = client.post(
        "/v1/orgs/" + client.org_id + "/operations/proposals",
        headers=headers(), json=proposal_payload,
    )
    assert response.status_code == 201, response.text
    db = client.session_factory()
    try:
        proposal = db.query(Proposal).filter_by(id=response.json()["id"]).one()
        now = datetime.now(timezone.utc)
        approval = Approval(
            org_id=client.org_id, workspace_id=client.ws_id,
            action_type="pricing.change", resource_id=proposal.id,
            idempotency_key="test-pricing-approved:" + proposal.id,
            request_payload={"amount_minor": proposal.amount_minor, "currency": proposal.currency},
            status=ApprovalStatus.approved, requested_by=client.user_id,
            decided_by=client.user_id, decision_note="Founder approved pricing",
            decided_at=now, consumed_at=now, consumed_by=client.user_id,
        )
        db.add(approval)
        db.flush()
        proposal.status = "approved"
        proposal.approval_id = approval.id
        proposal.approved_by = client.user_id
        proposal.approved_at = now
        db.commit()
    finally:
        db.close()
    return response.json()["id"]


def test_contract_snapshots_retainer_commercial_terms(client):
    proposal_id = _create_approved_proposal_for_contract(client, {
        "engagement_type": "retainer", "billing_frequency": "monthly",
        "term_months": 12, "included_hours_per_period": 60,
        "rollover_hours": True, "support_response_hours": 4,
        "auto_renew": False,
    })
    created = client.post(
        "/v1/orgs/" + client.org_id + "/operations/contracts",
        headers=headers(), json={
            "workspace_id": client.ws_id, "proposal_id": proposal_id,
            "contract_number": "AG-2026-RETAINER", "title": "Managed AI Services Retainer",
        },
    )
    assert created.status_code == 201, created.text
    terms = created.json()["terms_snapshot"]
    assert terms["engagement_type"] == "retainer"
    assert terms["billing_frequency"] == "monthly"
    assert terms["term_months"] == 12
    assert terms["included_hours_per_period"] == 60
    assert terms["rollover_hours"] is True
    assert terms["support_response_hours"] == 4
    assert terms["auto_renew"] is False


def test_contract_requires_approved_proposal_and_records_signed_evidence(client):
    org, ws = client.org_id, client.ws_id
    draft_proposal = client.post(
        "/v1/orgs/" + org + "/operations/proposals",
        headers=headers(), json={
            "workspace_id": ws, "opportunity_id": client.opportunity_id,
            "title": "Unapproved proposal", "service_line": "AI Engineering",
            "scope_summary": "This proposal is not yet approved for contract preparation.",
            "amount_minor": 500000, "currency": "INR",
        },
    )
    assert draft_proposal.status_code == 201
    blocked = client.post(
        "/v1/orgs/" + org + "/operations/contracts",
        headers=headers(), json={
            "workspace_id": ws, "proposal_id": draft_proposal.json()["id"],
            "contract_number": "AG-2026-001", "title": "Client AI Services Agreement",
        },
    )
    assert blocked.status_code == 409

    proposal_id = _create_approved_proposal_for_contract(client)
    created = client.post(
        "/v1/orgs/" + org + "/operations/contracts",
        headers=headers(), json={
            "workspace_id": ws, "proposal_id": proposal_id,
            "contract_number": "AG-2026-002", "title": "Client AI Services Agreement",
        },
    )
    assert created.status_code == 201, created.text
    contract_id = created.json()["id"]
    assert created.json()["status"] == "draft"
    assert created.json()["amount_minor"] == 1800000
    assert created.json()["terms_snapshot"]["proposal_id"] == proposal_id

    submitted = client.post(
        "/v1/orgs/" + org + "/operations/contracts/" + contract_id + "/submit-for-approval",
        headers=headers(),
    )
    assert submitted.status_code == 200, submitted.text
    approval_id = submitted.json()["approval_id"]

    db = client.session_factory()
    try:
        approval = db.query(Approval).filter_by(id=approval_id).one()
        approval.status = ApprovalStatus.approved
        approval.decided_by = client.user_id
        approval.decided_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()

    missing_evidence = client.post(
        "/v1/orgs/" + org + "/operations/contracts/" + contract_id + "/record-execution",
        headers=headers(), json={
            "approval_id": approval_id, "signed_reference": " ",
            "signed_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert missing_evidence.status_code == 422

    executed = client.post(
        "/v1/orgs/" + org + "/operations/contracts/" + contract_id + "/record-execution",
        headers=headers(), json={
            "approval_id": approval_id, "signed_reference": "signed-copy://AG-2026-002",
            "signed_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert executed.status_code == 200, executed.text
    assert executed.json()["status"] == "executed"
    assert executed.json()["signed_reference"] == "signed-copy://AG-2026-002"

    db = client.session_factory()
    try:
        approval = db.query(Approval).filter_by(id=approval_id).one()
        assert approval.consumed_at is not None
        assert approval.consumed_by == client.user_id
    finally:
        db.close()

    replay = client.post(
        "/v1/orgs/" + org + "/operations/contracts/" + contract_id + "/record-execution",
        headers=headers(), json={
            "approval_id": approval_id, "signed_reference": "signed-copy://AG-2026-002",
            "signed_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert replay.status_code == 409



def test_founder_can_reject_contract_execution_and_approval_together(client):
    proposal_id = _create_approved_proposal_for_contract(client)
    created = client.post(
        "/v1/orgs/" + client.org_id + "/operations/contracts",
        headers=headers(), json={
            "workspace_id": client.ws_id, "proposal_id": proposal_id,
            "contract_number": "AG-2026-REJECT", "title": "Rejected Agreement",
        },
    )
    assert created.status_code == 201, created.text
    contract_id = created.json()["id"]
    submitted = client.post(
        "/v1/orgs/" + client.org_id + "/operations/contracts/" + contract_id + "/submit-for-approval",
        headers=headers(),
    )
    assert submitted.status_code == 200, submitted.text
    approval_id = submitted.json()["approval_id"]
    rejected = client.post(
        "/v1/orgs/" + client.org_id + "/operations/contracts/" + contract_id + "/reject",
        headers=headers(), json={"approval_id": approval_id, "note": "Commercial terms need revision"},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"
    db = client.session_factory()
    try:
        approval = db.query(Approval).filter_by(id=approval_id).one()
        assert approval.status == ApprovalStatus.rejected
        assert approval.decided_by == client.user_id
    finally:
        db.close()



def _create_executed_contract(client, contract_number="AG-2026-ONBOARD"):
    proposal_id = _create_approved_proposal_for_contract(client)
    created = client.post(
        "/v1/orgs/" + client.org_id + "/operations/contracts",
        headers=headers(), json={
            "workspace_id": client.ws_id, "proposal_id": proposal_id,
            "contract_number": contract_number, "title": "Client AI Services Agreement",
        },
    )
    assert created.status_code == 201, created.text
    contract_id = created.json()["id"]
    submitted = client.post(
        "/v1/orgs/" + client.org_id + "/operations/contracts/" + contract_id + "/submit-for-approval",
        headers=headers(),
    )
    assert submitted.status_code == 200, submitted.text
    approval_id = submitted.json()["approval_id"]
    db = client.session_factory()
    try:
        approval = db.query(Approval).filter_by(id=approval_id).one()
        approval.status = ApprovalStatus.approved
        approval.decided_by = client.user_id
        approval.decided_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()
    executed = client.post(
        "/v1/orgs/" + client.org_id + "/operations/contracts/" + contract_id + "/record-execution",
        headers=headers(), json={
            "approval_id": approval_id, "signed_reference": "signed-copy://" + contract_number,
            "signed_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert executed.status_code == 200, executed.text
    return contract_id


def test_onboarding_requires_executed_contract_checklist_and_delivery_approval(client):
    org, ws = client.org_id, client.ws_id
    draft_proposal = client.post(
        "/v1/orgs/" + org + "/operations/proposals",
        headers=headers(), json={
            "workspace_id": ws, "opportunity_id": client.opportunity_id,
            "title": "Not ready for onboarding", "service_line": "AI Engineering",
            "scope_summary": "This proposal has not reached the executed contract stage.",
            "amount_minor": 250000, "currency": "INR",
        },
    )
    assert draft_proposal.status_code == 201
    unapproved_contract = client.post(
        "/v1/orgs/" + org + "/operations/contracts",
        headers=headers(), json={
            "workspace_id": ws, "proposal_id": draft_proposal.json()["id"],
            "contract_number": "AG-2026-NO-ONBOARD", "title": "Not signed",
        },
    )
    assert unapproved_contract.status_code == 409

    contract_id = _create_executed_contract(client)
    created = client.post(
        "/v1/orgs/" + org + "/operations/onboardings",
        headers=headers(), json={"workspace_id": ws, "contract_id": contract_id},
    )
    assert created.status_code == 201, created.text
    onboarding_id = created.json()["id"]
    assert created.json()["status"] == "preparing"

    duplicate = client.post(
        "/v1/orgs/" + org + "/operations/onboardings",
        headers=headers(), json={"workspace_id": ws, "contract_id": contract_id},
    )
    assert duplicate.status_code == 409

    checklist = client.get(
        "/v1/orgs/" + org + "/operations/onboardings/" + onboarding_id + "/checklist",
        headers=headers(),
    )
    assert checklist.status_code == 200, checklist.text
    assert len(checklist.json()) == 6

    plan = {
        "project_name": "Acme AI Workflow Delivery",
        "budget_minor": 900000,
        "estimated_hours": 120,
        "due_date": "2027-02-15T12:00:00+00:00",
    }
    blocked = client.post(
        "/v1/orgs/" + org + "/operations/onboardings/" + onboarding_id + "/submit-for-activation",
        headers=headers(), json=plan,
    )
    assert blocked.status_code == 409

    for item in checklist.json():
        updated = client.patch(
            "/v1/orgs/" + org + "/operations/onboardings/" + onboarding_id + "/checklist/" + item["id"],
            headers=headers(), json={"status": "completed", "note": "Reviewed and confirmed with the client."},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["status"] == "completed"

    submitted = client.post(
        "/v1/orgs/" + org + "/operations/onboardings/" + onboarding_id + "/submit-for-activation",
        headers=headers(), json=plan,
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "pending_approval"
    approval_id = submitted.json()["approval_id"]

    db = client.session_factory()
    try:
        approval = db.query(Approval).filter_by(id=approval_id).one()
        approval.status = ApprovalStatus.approved
        approval.decided_by = client.user_id
        approval.decided_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()

    activated = client.post(
        "/v1/orgs/" + org + "/operations/onboardings/" + onboarding_id + "/activate",
        headers=headers(),
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "active"
    project_id = activated.json()["project_id"]
    assert project_id

    db = client.session_factory()
    try:
        project = db.query(Project).filter_by(id=project_id, org_id=org, workspace_id=ws).one()
        assert project.client_id == client.client_id
        assert project.contract_value_minor == 1800000
        assert project.budget_minor == 900000
        assert project.status == "planned"
        approval = db.query(Approval).filter_by(id=approval_id).one()
        assert approval.consumed_at is not None
        assert approval.consumed_by == client.user_id
    finally:
        db.close()

    replay = client.post(
        "/v1/orgs/" + org + "/operations/onboardings/" + onboarding_id + "/activate",
        headers=headers(),
    )
    assert replay.status_code == 409



def test_rejected_delivery_activation_returns_to_preparation_for_retry(client):
    contract_id = _create_executed_contract(client, "AG-2026-RETRY")
    created = client.post(
        "/v1/orgs/" + client.org_id + "/operations/onboardings",
        headers=headers(), json={"workspace_id": client.ws_id, "contract_id": contract_id},
    )
    assert created.status_code == 201, created.text
    onboarding_id = created.json()["id"]
    checklist = client.get(
        "/v1/orgs/" + client.org_id + "/operations/onboardings/" + onboarding_id + "/checklist",
        headers=headers(),
    ).json()
    for item in checklist:
        updated = client.patch(
            "/v1/orgs/" + client.org_id + "/operations/onboardings/" + onboarding_id + "/checklist/" + item["id"],
            headers=headers(), json={"status": "completed", "note": "Confirmed for retry test."},
        )
        assert updated.status_code == 200, updated.text
    plan = {
        "project_name": "Retryable delivery project",
        "budget_minor": 500000, "estimated_hours": 60,
    }
    first = client.post(
        "/v1/orgs/" + client.org_id + "/operations/onboardings/" + onboarding_id + "/submit-for-activation",
        headers=headers(), json=plan,
    )
    assert first.status_code == 200, first.text
    first_approval_id = first.json()["approval_id"]
    rejected = client.post(
        "/v1/orgs/" + client.org_id + "/operations/onboardings/" + onboarding_id + "/reject-activation",
        headers=headers(), json={"approval_id": first_approval_id, "note": "Revise the delivery budget"},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "preparing"
    db = client.session_factory()
    try:
        first_approval = db.query(Approval).filter_by(id=first_approval_id).one()
        assert first_approval.status == ApprovalStatus.rejected
    finally:
        db.close()
    second = client.post(
        "/v1/orgs/" + client.org_id + "/operations/onboardings/" + onboarding_id + "/submit-for-activation",
        headers=headers(), json=plan,
    )
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "pending_approval"
    assert second.json()["approval_id"] != first_approval_id


def test_only_founder_can_waive_required_onboarding_checklist_item(client):
    contract_id = _create_executed_contract(client, "AG-2026-WAIVE")
    created = client.post(
        "/v1/orgs/" + client.org_id + "/operations/onboardings",
        headers=headers(), json={"workspace_id": client.ws_id, "contract_id": contract_id},
    )
    assert created.status_code == 201, created.text
    item = client.get(
        "/v1/orgs/" + client.org_id + "/operations/onboardings/" + created.json()["id"] + "/checklist",
        headers=headers(),
    ).json()[0]
    db = client.session_factory()
    try:
        founder = db.query(User).filter_by(id=client.user_id).one()
        operator = User(email="onboarding-operator@example.test", display_name="Operator")
        db.add(operator)
        db.flush()
        db.add(Membership(org_id=client.org_id, user_id=operator.id, role=Role.operator))
        db.commit()
        client.app.dependency_overrides[get_principal] = lambda: Principal(user=operator)
    finally:
        db.close()
    denied = client.patch(
        "/v1/orgs/" + client.org_id + "/operations/onboardings/" + created.json()["id"] + "/checklist/" + item["id"],
        headers=headers(), json={"status": "waived", "note": "Not applicable for this engagement"},
    )
    assert denied.status_code == 403
    client.app.dependency_overrides[get_principal] = lambda: Principal(user=founder)
    waived = client.patch(
        "/v1/orgs/" + client.org_id + "/operations/onboardings/" + created.json()["id"] + "/checklist/" + item["id"],
        headers=headers(), json={"status": "waived", "note": "Founder accepted this documented exception"},
    )
    assert waived.status_code == 200, waived.text
    assert waived.json()["status"] == "waived"


def test_contract_rejects_cross_workspace_proposal(client):
    response = client.post(
        "/v1/orgs/" + client.org_id + "/operations/contracts",
        headers=headers(), json={
            "workspace_id": client.other_ws_id, "proposal_id": "proposal-from-another-workspace",
            "contract_number": "AG-2026-003", "title": "Wrong workspace contract",
        },
    )
    assert response.status_code == 404



def test_founder_authority_viewer_can_read_commercial_and_delivery_registers(client):
    db = client.session_factory()
    try:
        founder_viewer = User(email="founder-viewer@example.test", display_name="Founder Viewer")
        db.add(founder_viewer)
        db.flush()
        db.add(Membership(org_id=client.org_id, user_id=founder_viewer.id, role=Role.viewer))
        db.add(FounderAuthority(org_id=client.org_id, user_id=founder_viewer.id, grant_source="test"))
        db.commit()
        client.app.dependency_overrides[get_principal] = lambda: Principal(user=founder_viewer)
    finally:
        db.close()
    for path in [
        "/service-catalog", "/proposals", "/contracts", "/onboardings",
    ]:
        response = client.get(
            "/v1/orgs/" + client.org_id + "/operations" + path,
            params={"workspace_id": client.ws_id}, headers=headers(),
        )
        assert response.status_code == 200, (path, response.text)



def test_invoice_issuance_and_partial_payment_reconciliation(client):
    contract_id = _create_executed_contract(client, "AG-2026-INVOICE")
    due_date = "2027-01-15T12:00:00+00:00"
    created = client.post(
        "/v1/orgs/" + client.org_id + "/operations/invoices",
        headers=headers(), json={
            "workspace_id": client.ws_id, "contract_id": contract_id,
            "invoice_number": "INV-2026-001", "title": "AI workflow milestone 1",
            "description": "Initial discovery and architecture milestone.",
            "line_items": [
                {"description": "Discovery and architecture", "amount_minor": 600000},
                {"description": "Initial implementation", "amount_minor": 400000},
            ],
            "due_date": due_date,
        },
    )
    assert created.status_code == 201, created.text
    invoice_id = created.json()["id"]
    assert created.json()["amount_minor"] == 1000000
    assert created.json()["paid_minor"] == 0
    assert created.json()["outstanding_minor"] == 1000000
    assert created.json()["status"] == "draft"

    over_contract = client.post(
        "/v1/orgs/" + client.org_id + "/operations/invoices",
        headers=headers(), json={
            "workspace_id": client.ws_id, "contract_id": contract_id,
            "invoice_number": "INV-2026-OVER", "title": "Overbilled milestone",
            "line_items": [{"description": "Overbilled", "amount_minor": 900000}],
            "due_date": due_date,
        },
    )
    assert over_contract.status_code == 422

    early_payment = client.post(
        "/v1/orgs/" + client.org_id + "/operations/invoices/" + invoice_id + "/payments",
        headers=headers(), json={
            "external_reference": "BANK-REF-001", "amount_minor": 100000,
            "payment_method": "bank_transfer", "source": "manual bank statement",
            "paid_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert early_payment.status_code == 409

    submitted = client.post(
        "/v1/orgs/" + client.org_id + "/operations/invoices/" + invoice_id + "/submit-for-approval",
        headers=headers(),
    )
    assert submitted.status_code == 200, submitted.text
    approval_id = submitted.json()["approval_id"]
    db = client.session_factory()
    try:
        approval = db.query(Approval).filter_by(id=approval_id).one()
        approval.status = ApprovalStatus.approved
        approval.decided_by = client.user_id
        approval.decided_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()

    issued = client.post(
        "/v1/orgs/" + client.org_id + "/operations/invoices/" + invoice_id + "/record-issued",
        headers=headers(), json={
            "approval_id": approval_id, "external_reference": "ACCOUNTING-INV-001",
            "issued_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert issued.status_code == 200, issued.text
    assert issued.json()["status"] == "issued"

    partial = client.post(
        "/v1/orgs/" + client.org_id + "/operations/invoices/" + invoice_id + "/payments",
        headers=headers(), json={
            "external_reference": "BANK-REF-001", "amount_minor": 300000,
            "payment_method": "bank_transfer", "source": "manual bank statement",
            "paid_at": datetime.now(timezone.utc).isoformat(), "notes": "First instalment",
        },
    )
    assert partial.status_code == 201, partial.text
    invoice = client.get(
        "/v1/orgs/" + client.org_id + "/operations/invoices",
        headers=headers(), params={"workspace_id": client.ws_id},
    )
    row = next(item for item in invoice.json() if item["id"] == invoice_id)
    assert row["status"] == "partially_paid"
    assert row["paid_minor"] == 300000
    assert row["outstanding_minor"] == 700000

    duplicate = client.post(
        "/v1/orgs/" + client.org_id + "/operations/invoices/" + invoice_id + "/payments",
        headers=headers(), json={
            "external_reference": "BANK-REF-001", "amount_minor": 100000,
            "payment_method": "bank_transfer", "source": "manual bank statement",
            "paid_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert duplicate.status_code == 409

    overpayment = client.post(
        "/v1/orgs/" + client.org_id + "/operations/invoices/" + invoice_id + "/payments",
        headers=headers(), json={
            "external_reference": "BANK-REF-002", "amount_minor": 800000,
            "payment_method": "bank_transfer", "source": "manual bank statement",
            "paid_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert overpayment.status_code == 422

    final_payment = client.post(
        "/v1/orgs/" + client.org_id + "/operations/invoices/" + invoice_id + "/payments",
        headers=headers(), json={
            "external_reference": "BANK-REF-003", "amount_minor": 700000,
            "payment_method": "upi", "source": "manual bank statement",
            "paid_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert final_payment.status_code == 201, final_payment.text
    assert final_payment.json()["amount_minor"] == 700000

    payments = client.get(
        "/v1/orgs/" + client.org_id + "/operations/invoices/" + invoice_id + "/payments",
        headers=headers(),
    )
    assert payments.status_code == 200
    assert len(payments.json()) == 2

    db = client.session_factory()
    try:
        invoice_record = db.query(InvoiceRecord).filter_by(id=invoice_id).one()
        assert invoice_record.status == "paid"
        assert invoice_record.paid_minor == invoice_record.amount_minor
        assert db.query(PaymentReceipt).filter_by(invoice_id=invoice_id).count() == 2
        approval = db.query(Approval).filter_by(id=approval_id).one()
        assert approval.consumed_at is not None
    finally:
        db.close()



def test_rejected_invoice_can_be_resubmitted_with_new_approval(client):
    contract_id = _create_executed_contract(client, "AG-2026-INVOICE-RETRY")
    created = client.post(
        "/v1/orgs/" + client.org_id + "/operations/invoices",
        headers=headers(), json={
            "workspace_id": client.ws_id, "contract_id": contract_id,
            "invoice_number": "INV-2026-RETRY", "title": "Retry invoice",
            "line_items": [{"description": "Milestone", "amount_minor": 100000}],
            "due_date": "2027-01-15T12:00:00+00:00",
        },
    )
    assert created.status_code == 201, created.text
    invoice_id = created.json()["id"]
    first = client.post(
        "/v1/orgs/" + client.org_id + "/operations/invoices/" + invoice_id + "/submit-for-approval",
        headers=headers(),
    )
    assert first.status_code == 200
    first_approval = first.json()["approval_id"]
    rejected = client.post(
        "/v1/orgs/" + client.org_id + "/operations/invoices/" + invoice_id + "/reject",
        headers=headers(), json={"approval_id": first_approval, "note": "Revise the milestone description"},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"
    second = client.post(
        "/v1/orgs/" + client.org_id + "/operations/invoices/" + invoice_id + "/submit-for-approval",
        headers=headers(),
    )
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "pending_approval"
    assert second.json()["approval_id"] != first_approval


def test_invoice_rejects_cross_workspace_contract_and_duplicate_invoice_number(client):
    missing = client.post(
        "/v1/orgs/" + client.org_id + "/operations/invoices",
        headers=headers(), json={
            "workspace_id": client.other_ws_id, "contract_id": "foreign-contract",
            "invoice_number": "INV-2026-X", "title": "Foreign invoice",
            "line_items": [{"description": "No access", "amount_minor": 1000}],
            "due_date": "2027-01-15T12:00:00+00:00",
        },
    )
    assert missing.status_code == 404

    contract_id = _create_executed_contract(client, "AG-2026-INVOICE-DUP")
    payload = {
        "workspace_id": client.ws_id, "contract_id": contract_id,
        "invoice_number": "INV-2026-DUP", "title": "Duplicate invoice test",
        "line_items": [{"description": "Milestone", "amount_minor": 100000}],
        "due_date": "2027-01-15T12:00:00+00:00",
    }
    first = client.post(
        "/v1/orgs/" + client.org_id + "/operations/invoices",
        headers=headers(), json=payload,
    )
    assert first.status_code == 201, first.text
    second = client.post(
        "/v1/orgs/" + client.org_id + "/operations/invoices",
        headers=headers(), json=payload,
    )
    assert second.status_code == 409



def test_invoice_issuance_and_partial_payment_reconciliation(client):
    contract_id = _create_executed_contract(client, "AG-2026-INVOICE")
    due_date = "2027-01-15T12:00:00+00:00"
    created = client.post(
        "/v1/orgs/" + client.org_id + "/operations/invoices",
        headers=headers(), json={
            "workspace_id": client.ws_id, "contract_id": contract_id,
            "invoice_number": "INV-2026-001", "title": "AI workflow milestone 1",
            "description": "Initial discovery and architecture milestone.",
            "line_items": [
                {"description": "Discovery and architecture", "amount_minor": 600000},
                {"description": "Initial implementation", "amount_minor": 400000},
            ],
            "due_date": due_date,
        },
    )
    assert created.status_code == 201, created.text
    invoice_id = created.json()["id"]
    assert created.json()["amount_minor"] == 1000000
    assert created.json()["paid_minor"] == 0
    assert created.json()["outstanding_minor"] == 1000000
    assert created.json()["status"] == "draft"

    over_contract = client.post(
        "/v1/orgs/" + client.org_id + "/operations/invoices",
        headers=headers(), json={
            "workspace_id": client.ws_id, "contract_id": contract_id,
            "invoice_number": "INV-2026-OVER", "title": "Overbilled milestone",
            "line_items": [{"description": "Overbilled", "amount_minor": 900000}],
            "due_date": due_date,
        },
    )
    assert over_contract.status_code == 422

    early_payment = client.post(
        "/v1/orgs/" + client.org_id + "/operations/invoices/" + invoice_id + "/payments",
        headers=headers(), json={
            "external_reference": "BANK-REF-001", "amount_minor": 100000,
            "payment_method": "bank_transfer", "source": "manual bank statement",
            "paid_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert early_payment.status_code == 409

    submitted = client.post(
        "/v1/orgs/" + client.org_id + "/operations/invoices/" + invoice_id + "/submit-for-approval",
        headers=headers(),
    )
    assert submitted.status_code == 200, submitted.text
    approval_id = submitted.json()["approval_id"]
    premature = client.post(
        "/v1/orgs/" + client.org_id + "/operations/invoices/" + invoice_id + "/record-issued",
        headers=headers(), json={
            "approval_id": approval_id, "external_reference": "ACCOUNTING-INV-001",
            "issued_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert premature.status_code == 409

    db = client.session_factory()
    try:
        approval = db.query(Approval).filter_by(id=approval_id).one()
        approval.status = ApprovalStatus.approved
        approval.decided_by = client.user_id
        approval.decided_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()

    issued = client.post(
        "/v1/orgs/" + client.org_id + "/operations/invoices/" + invoice_id + "/record-issued",
        headers=headers(), json={
            "approval_id": approval_id, "external_reference": "ACCOUNTING-INV-001",
            "issued_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert issued.status_code == 200, issued.text
    assert issued.json()["status"] == "issued"

    partial = client.post(
        "/v1/orgs/" + client.org_id + "/operations/invoices/" + invoice_id + "/payments",
        headers=headers(), json={
            "external_reference": "BANK-REF-001", "amount_minor": 300000,
            "payment_method": "bank_transfer", "source": "manual bank statement",
            "paid_at": datetime.now(timezone.utc).isoformat(), "notes": "First instalment",
        },
    )
    assert partial.status_code == 201, partial.text
    invoice = client.get(
        "/v1/orgs/" + client.org_id + "/operations/invoices",
        headers=headers(), params={"workspace_id": client.ws_id},
    )
    row = next(item for item in invoice.json() if item["id"] == invoice_id)
    assert row["status"] == "partially_paid"
    assert row["paid_minor"] == 300000
    assert row["outstanding_minor"] == 700000

    duplicate = client.post(
        "/v1/orgs/" + client.org_id + "/operations/invoices/" + invoice_id + "/payments",
        headers=headers(), json={
            "external_reference": "BANK-REF-001", "amount_minor": 100000,
            "payment_method": "bank_transfer", "source": "manual bank statement",
            "paid_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert duplicate.status_code == 409

    overpayment = client.post(
        "/v1/orgs/" + client.org_id + "/operations/invoices/" + invoice_id + "/payments",
        headers=headers(), json={
            "external_reference": "BANK-REF-002", "amount_minor": 800000,
            "payment_method": "bank_transfer", "source": "manual bank statement",
            "paid_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert overpayment.status_code == 422

    final_payment = client.post(
        "/v1/orgs/" + client.org_id + "/operations/invoices/" + invoice_id + "/payments",
        headers=headers(), json={
            "external_reference": "BANK-REF-003", "amount_minor": 700000,
            "payment_method": "upi", "source": "manual bank statement",
            "paid_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert final_payment.status_code == 201, final_payment.text

    payments = client.get(
        "/v1/orgs/" + client.org_id + "/operations/invoices/" + invoice_id + "/payments",
        headers=headers(),
    )
    assert payments.status_code == 200
    assert len(payments.json()) == 2
    immutable = client.patch(
        "/v1/orgs/" + client.org_id + "/operations/invoices/" + invoice_id + "/payments/" + final_payment.json()["id"],
        headers=headers(), json={"amount_minor": 1},
    )
    assert immutable.status_code == 404

    db = client.session_factory()
    try:
        invoice_record = db.query(InvoiceRecord).filter_by(id=invoice_id).one()
        assert invoice_record.status == "paid"
        assert invoice_record.paid_minor == invoice_record.amount_minor
        assert db.query(PaymentReceipt).filter_by(invoice_id=invoice_id).count() == 2
        approval = db.query(Approval).filter_by(id=approval_id).one()
        assert approval.consumed_at is not None
    finally:
        db.close()


def test_invoice_rejects_cross_workspace_contract_and_duplicate_invoice_number(client):
    missing = client.post(
        "/v1/orgs/" + client.org_id + "/operations/invoices",
        headers=headers(), json={
            "workspace_id": client.other_ws_id, "contract_id": "foreign-contract",
            "invoice_number": "INV-2026-X", "title": "Foreign invoice",
            "line_items": [{"description": "No access", "amount_minor": 1000}],
            "due_date": "2027-01-15T12:00:00+00:00",
        },
    )
    assert missing.status_code == 404

    contract_id = _create_executed_contract(client, "AG-2026-INVOICE-DUP")
    payload = {
        "workspace_id": client.ws_id, "contract_id": contract_id,
        "invoice_number": "INV-2026-DUP", "title": "Duplicate invoice test",
        "line_items": [{"description": "Milestone", "amount_minor": 100000}],
        "due_date": "2027-01-15T12:00:00+00:00",
    }
    first = client.post(
        "/v1/orgs/" + client.org_id + "/operations/invoices",
        headers=headers(), json=payload,
    )
    assert first.status_code == 201, first.text
    second = client.post(
        "/v1/orgs/" + client.org_id + "/operations/invoices",
        headers=headers(), json=payload,
    )
    assert second.status_code == 409


def test_time_and_cost_roll_up_to_project_financial_summary(client):
    org, ws, project = client.org_id, client.ws_id, client.project_id
    t = client.post(f"/v1/orgs/{org}/operations/time-entries", headers=headers(), json={
        "workspace_id": ws, "project_id": project, "description": "Implement retrieval pipeline",
        "duration_minutes": 120, "billable": True, "hourly_cost_minor": 30000,
        "started_at": "2026-11-24T09:00:00Z",
    })
    assert t.status_code == 201, t.text
    c = client.post(f"/v1/orgs/{org}/operations/project-costs", headers=headers(), json={
        "workspace_id": ws, "project_id": project, "category": "cloud",
        "description": "Development environment", "amount_minor": 50000,
        "currency": "INR", "incurred_at": "2026-11-24T10:00:00Z",
    })
    assert c.status_code == 201, c.text
    summary = client.get(
        f"/v1/orgs/{org}/operations/projects/{project}/financial-summary",
        params={"workspace_id": ws}, headers=headers(),
    )
    assert summary.status_code == 200, summary.text
    data = summary.json()
    assert data["actual_minutes"] == 120
    assert data["labor_cost_minor"] == 60000
    assert data["other_cost_minor"] == 50000
    assert data["actual_cost_minor"] == 110000
    assert data["gross_margin_minor"] == 1090000
    assert data["budget_remaining_minor"] == 390000
    assert data["margin_is_provisional"] is True


def test_scope_change_requires_single_use_founder_approval(client):
    org, ws, project = client.org_id, client.ws_id, client.project_id
    change = client.post(f"/v1/orgs/{org}/operations/scope-changes", headers=headers(), json={
        "workspace_id": ws, "project_id": project, "title": "Add a second data source",
        "description": "Include another internal repository",
        "impact_summary": "Additional connector and regression coverage",
        "estimated_hours_delta": 12, "budget_delta_minor": 40000,
        "contract_value_delta_minor": 90000, "schedule_days_delta": 5,
    })
    assert change.status_code == 201, change.text
    change_id = change.json()["id"]

    # No approval means no commercial or schedule mutation.
    denied = client.post(
        f"/v1/orgs/{org}/operations/scope-changes/{change_id}/approve",
        headers=headers(), json={"approval_id": "missing-approval"},
    )
    assert denied.status_code == 403

    from app.db import get_db as db_dependency
    session_gen = client.app.dependency_overrides[db_dependency]()
    db = next(session_gen)
    try:
        approval = Approval(
            org_id=org, workspace_id=ws, action_type="scope.change.accept",
            resource_id=change_id, idempotency_key="scope-approval-1",
            request_payload={"reason": "Founder-approved scope change"},
            status=ApprovalStatus.approved, requested_by=client.user_id,
            decided_by=client.user_id, decision_note="Approved",
            decided_at=datetime.now(timezone.utc),
        )
        db.add(approval)
        db.commit()
        approval_id = approval.id
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass

    accepted = client.post(
        f"/v1/orgs/{org}/operations/scope-changes/{change_id}/approve",
        headers=headers(), json={"approval_id": approval_id},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "approved"

    again = client.post(
        f"/v1/orgs/{org}/operations/scope-changes/{change_id}/approve",
        headers=headers(), json={"approval_id": approval_id},
    )
    assert again.status_code == 409


def test_project_currency_must_match_cost_currency(client):
    r = client.post(f"/v1/orgs/{client.org_id}/operations/project-costs", headers=headers(), json={
        "workspace_id": client.ws_id, "project_id": client.project_id,
        "category": "cloud", "description": "Cloud bill", "amount_minor": 100,
        "currency": "USD", "incurred_at": "2026-11-24T10:00:00Z",
    })
    assert r.status_code == 422


def test_cross_workspace_project_is_not_visible(client):
    r = client.get(
        f"/v1/orgs/{client.org_id}/operations/projects/{client.project_id}/financial-summary",
        params={"workspace_id": client.other_ws_id}, headers=headers(),
    )
    assert r.status_code == 404



def test_founder_exception_inbox_surfaces_pending_approvals_and_blocked_tasks(client):
    db = client.session_factory()
    try:
        db.add(Approval(
            org_id=client.org_id, workspace_id=client.ws_id,
            action_type="pricing.change", resource_id="quote-1",
            idempotency_key="pending-pricing-approval",
            request_payload={"reason": "Price review"},
            status=ApprovalStatus.pending, requested_by=client.user_id,
        ))
        db.add(Task(
            org_id=client.org_id, workspace_id=client.ws_id,
            title="Resolve provider failure", status="blocked",
            created_by=client.user_id,
        ))
        db.commit()
    finally:
        db.close()
    r = client.get(
        f"/v1/orgs/{client.org_id}/operations/exceptions",
        params={"workspace_id": client.ws_id}, headers=headers(),
    )
    assert r.status_code == 200, r.text
    kinds = {item["kind"] for item in r.json()["items"]}
    assert {"approval", "blocked_task"} <= kinds


def test_agent_performance_is_workspace_scoped(client):
    r = client.get(
        f"/v1/orgs/{client.org_id}/operations/agent-performance",
        params={"workspace_id": client.ws_id}, headers=headers(),
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"items": []}

def test_outbox_health_is_founder_only_and_org_scoped(client):
    db = client.session_factory()
    try:
        db.add_all([
            OutboxEvent(
                org_id=client.org_id,
                workspace_id=client.ws_id,
                event_type="test.pending",
                schema_version=1,
                aggregate_type="test",
                aggregate_id="pending-1",
                idempotency_key="health-pending-1",
                payload={"must_not_be_exposed": True},
                status="pending",
                attempts=0,
            ),
            OutboxEvent(
                org_id=client.org_id,
                workspace_id=client.ws_id,
                event_type="test.retry",
                schema_version=1,
                aggregate_type="test",
                aggregate_id="retry-1",
                idempotency_key="health-retry-1",
                payload={},
                status="pending",
                attempts=2,
            ),
            OutboxEvent(
                org_id=client.org_id,
                workspace_id=client.ws_id,
                event_type="test.dead",
                schema_version=1,
                aggregate_type="test",
                aggregate_id="dead-1",
                idempotency_key="health-dead-1",
                payload={},
                status="dead_letter",
                attempts=8,
            ),
            OutboxEvent(
                org_id=client.other_ws_id,
                workspace_id=client.other_ws_id,
                event_type="test.other",
                schema_version=1,
                aggregate_type="test",
                aggregate_id="other-1",
                idempotency_key="health-other-1",
                payload={},
                status="dead_letter",
                attempts=8,
            ),
        ])
        db.commit()
    finally:
        db.close()

    response = client.get(
        f"/v1/orgs/{client.org_id}/operations/outbox-health",
        headers=headers(),
    )

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["pending_count"] == 2
    assert data["retrying_count"] == 1
    assert data["dead_letter_count"] == 1
    assert "payload" not in data
    assert "idempotency_key" not in data
    assert "worker_id" not in data

def test_outbox_health_denies_member_without_founder_authority(client):
    db = client.session_factory()
    try:
        member = User(
            email="ordinary-member@example.test",
            display_name="Ordinary Member",
        )
        db.add(member)
        db.flush()

        db.add(Membership(
            org_id=client.org_id,
            user_id=member.id,
            role=Role.operator,
        ))
        db.commit()

        client.app.dependency_overrides[get_principal] = (
            lambda: Principal(user=member)
        )

        response = client.get(
            f"/v1/orgs/{client.org_id}/operations/outbox-health",
            headers=headers(),
        )

        assert response.status_code == 403
    finally:
        client.app.dependency_overrides.pop(get_principal, None)
        db.close()