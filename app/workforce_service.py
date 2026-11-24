"""Idempotent provisioning of the full target agency workforce chart."""
"""Initialize the target workforce chart without activating external autonomy."""
from __future__ import annotations

from sqlalchemy.orm import Session
from app.models import Agent, Workspace
from app.workforce_models import WorkforceUnit, WorkforceMember


DEPARTMENTS = [
    ("marketing_brand", "Marketing & Brand", "growth", "Brand, content, SEO, social and growth marketing."),
    ("business_development_sales", "Business Development & Sales", "growth", "Lead generation, qualification, CRM and proposals."),
    ("market_research_intelligence", "Market Research & Intelligence", "growth", "Market, sector, competitor and opportunity research."),
    ("solutions_consulting_strategy", "Solutions Consulting & Strategy", "strategy_commercial", "Discovery, feasibility, architecture and presales."),
    ("finance_accounts", "Finance & Accounts", "strategy_commercial", "Management finance, budgets, receivables and project margin."),
    ("legal_risk_compliance", "Legal, Risk & Compliance", "strategy_commercial", "Contract review support, privacy, licensing and risk."),
    ("ai_research_innovation", "AI Research & Innovation", "technology", "Model, agent, RAG, vision, speech and evaluation research."),
    ("ai_engineering_development", "AI Engineering & Development", "technology", "AI/ML, LLM, backend, frontend and data engineering."),
    ("automation_integration_engineering", "Automation & Integration Engineering", "technology", "Workflow, API, MCP and integration engineering."),
    ("infrastructure_it_operations", "Infrastructure & IT Operations", "technology", "Cloud, platform, database, SRE and internal IT."),
    ("pmo", "Project Management Office", "delivery_quality", "Plans, dependencies, capacity, risks and reporting."),
    ("delivery_implementation", "Delivery & Implementation", "delivery_quality", "Onboarding, implementation, deployment and handover."),
    ("quality_assurance_security", "Quality Assurance & Security", "delivery_quality", "Independent QA, evaluation, application and data security."),
    ("client_success_support", "Client Success & Support", "business_operations", "Client onboarding, relationship, support and account growth."),
    ("hr_people_operations", "HR & People Operations", "business_operations", "Talent, workforce operations, learning and culture."),
    ("administration_procurement", "Administration & Procurement", "business_operations", "Administration, procurement, vendors and subscriptions."),
]

GROUPS = [
    ("growth", "Growth"),
    ("strategy_commercial", "Strategy & Commercial"),
    ("technology", "Technology & Innovation"),
    ("delivery_quality", "Execution & Quality"),
    ("business_operations", "Business Operations & Relationships"),
]


def initialize_workforce(db: Session, *, org_id: str, workspace_id: str) -> dict:
    """Idempotently provision the 16-department target chart with inactive members."""
    workspace = db.query(Workspace).filter_by(id=workspace_id, org_id=org_id).first()
    if workspace is None:
        raise ValueError("Workspace not found")
    office = db.query(WorkforceUnit).filter_by(
        org_id=org_id, workspace_id=workspace_id, department_key="office", name="Office of the CEO"
    ).one_or_none()
    if office is None:
        office = WorkforceUnit(org_id=org_id, workspace_id=workspace_id,
                               name="Office of the CEO", unit_type="office", department_key="office",
                               description="Founder authority and executive coordination.")
        db.add(office)
        db.flush()

    existing_group_members = {
        member.department_key: member
        for member in db.query(WorkforceMember).filter_by(
            org_id=org_id, workspace_id=workspace_id, member_type="supervisor"
        ).all()
        if member.department_key.startswith("office_")
    }
    if "office_founder" not in existing_group_members:
        db.add(WorkforceMember(
            org_id=org_id, workspace_id=workspace_id, unit_id=office.id,
            member_type="human", name="Founder / CEO", title="Founder / Chief Executive Officer",
            department_key="office_founder", responsibilities=[
                "Strategy and priorities", "Final commercial authority",
                "Protected approvals", "Financial commitments", "Production releases",
            ], autonomy_level=0, status="planned", is_founder_reserved=True,
        ))
        db.flush()
    founder = db.query(WorkforceMember).filter_by(
        org_id=org_id, workspace_id=workspace_id, department_key="office_founder",
    ).one()
    if "office_chief_of_staff" not in existing_group_members:
        db.add(WorkforceMember(
            org_id=org_id, workspace_id=workspace_id, unit_id=office.id,
            member_type="supervisor", name="Chief of Staff / Claude Agency Supervisor",
            title="Chief of Staff & Agency Supervisor", department_key="office_chief_of_staff",
            responsibilities=["Convert founder priorities into plans", "Coordinate department heads",
                               "Track dependencies, exceptions and execution", "Prepare founder decision briefs"],
            autonomy_level=2, status="planned", is_founder_reserved=False,
        ))
        db.flush()
    chief = db.query(WorkforceMember).filter_by(
        org_id=org_id, workspace_id=workspace_id, department_key="office_chief_of_staff",
    ).one()
    # Executive Assistant remains a distinct role and does not own protected authority.
    assistant = db.query(WorkforceMember).filter_by(
        org_id=org_id, workspace_id=workspace_id, department_key="office_executive_assistant",
    ).one_or_none()
    if assistant is None:
        assistant = WorkforceMember(
            org_id=org_id, workspace_id=workspace_id, unit_id=office.id,
            manager_member_id=chief.id, member_type="agent", name="Executive Assistant",
            title="Executive Assistant", department_key="office_executive_assistant",
            responsibilities=["Prepare briefs", "Coordinate internal scheduling", "Track reminders"],
            autonomy_level=1, status="planned",
        )
        db.add(assistant)

    group_units = {}
    for key, name in GROUPS:
        unit = db.query(WorkforceUnit).filter_by(
            org_id=org_id, workspace_id=workspace_id, department_key=key, name=name
        ).one_or_none()
        if unit is None:
            unit = WorkforceUnit(org_id=org_id, workspace_id=workspace_id, parent_unit_id=office.id,
                                 name=name, unit_type="group", department_key=key,
                                 description=f"{name} functional group.")
            db.add(unit)
            db.flush()
        group_units[key] = unit

    dept_group = {row[0]: row[2] for row in DEPARTMENTS}
    dept_names = {row[0]: row[1] for row in DEPARTMENTS}
    for key, name, group_key, description in DEPARTMENTS:
        unit = db.query(WorkforceUnit).filter_by(
            org_id=org_id, workspace_id=workspace_id, department_key=key, name=name
        ).one_or_none()
        if unit is None:
            unit = WorkforceUnit(org_id=org_id, workspace_id=workspace_id,
                                 parent_unit_id=group_units[group_key].id, name=name,
                                 unit_type="department", department_key=key,
                                 description=description)
            db.add(unit)
            db.flush()
        head_key = f"{key}_head"
        head = db.query(WorkforceMember).filter_by(
            org_id=org_id, workspace_id=workspace_id, department_key=head_key
        ).one_or_none()
        if head is None:
            head = WorkforceMember(
                org_id=org_id, workspace_id=workspace_id, unit_id=unit.id,
                manager_member_id=chief.id, member_type="supervisor",
                name=f"Head of {name}", title=f"Department Head — {name}",
                department_key=head_key, responsibilities=[f"Coordinate {name}", "Assign reviewed work",
                                                            "Report department status and risks"],
                autonomy_level=2, status="planned",
            )
            db.add(head)
        else:
            head.unit_id = unit.id
            head.manager_member_id = chief.id
        existing_agent = db.query(Agent).filter_by(
            org_id=org_id, workspace_id=workspace_id, name=f"{name} Specialist"
        ).one_or_none()
        if existing_agent is None:
            existing_agent = Agent(
                org_id=org_id, workspace_id=workspace_id,
                name=f"{name} Specialist", department=name,
                instructions=f"Department specialist for {name}. {description}",
                runtime="claude_managed_agents", data_class="synthetic", enabled=False,
            )
            db.add(existing_agent)
            db.flush()
        existing_member = db.query(WorkforceMember).filter_by(
            org_id=org_id, workspace_id=workspace_id, department_key=key
        ).one_or_none()
        if existing_member is None:
            existing_member = WorkforceMember(
                org_id=org_id, workspace_id=workspace_id, unit_id=unit.id,
                manager_member_id=head.id, agent_id=existing_agent.id,
                member_type="agent", name=f"{name} Specialist", title=f"{name} Specialist",
                department_key=key, responsibilities=[description, "Produce evidence-backed recommendations",
                                                      "Escalate approval-required actions"],
                autonomy_level=1, status="planned",
            )
            db.add(existing_member)
        else:
            existing_member.unit_id = unit.id
            existing_member.manager_member_id = head.id
            existing_member.agent_id = existing_agent.id
    db.flush()
    return {
        "office_units": 1,
        "functional_groups": len(GROUPS),
        "departments": len(DEPARTMENTS),
        "department_heads": len(DEPARTMENTS),
        "specialists": len(DEPARTMENTS),
        "founder_reserved": 1,
    }
