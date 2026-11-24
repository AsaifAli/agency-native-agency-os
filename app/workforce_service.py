"""Idempotent provisioning of the full founder-governed agency workforce."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Agent, Workspace
from app.workforce_models import WorkforceUnit, WorkforceMember, WorkforcePosition
from app.workforce_catalog import (
    DEPARTMENT_TEAMS,
    GROUPS as CATALOG_GROUPS,
    HEAD_TITLES,
    HEAD_RESPONSIBILITIES,
    build_positions,
    key_for,
)

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


def _unit(db: Session, *, org_id: str, workspace_id: str, parent_id: str | None,
          name: str, unit_type: str, department_key: str, description: str = "") -> WorkforceUnit:
    row = db.query(WorkforceUnit).filter_by(
        org_id=org_id, workspace_id=workspace_id, department_key=department_key, name=name
    ).one_or_none()
    if row is None:
        row = WorkforceUnit(
            org_id=org_id, workspace_id=workspace_id, parent_unit_id=parent_id,
            name=name, unit_type=unit_type, department_key=department_key,
            description=description,
        )
        db.add(row)
        db.flush()
    elif row.parent_unit_id != parent_id:
        row.parent_unit_id = parent_id
    return row


def _agent(db: Session, *, org_id: str, workspace_id: str, name: str,
           department: str, instructions: str) -> Agent:
    row = db.query(Agent).filter_by(org_id=org_id, workspace_id=workspace_id, name=name).one_or_none()
    if row is None:
        row = Agent(
            org_id=org_id, workspace_id=workspace_id, name=name, department=department,
            instructions=instructions, runtime="claude_managed_agents",
            data_class="synthetic", enabled=False,
        )
        db.add(row)
        db.flush()
    return row


def _member(db: Session, *, org_id: str, workspace_id: str, unit_id: str,
            manager_id: str | None, member_type: str, name: str, title: str,
            department_key: str, responsibilities: list[str], autonomy: int,
            agent_id: str | None = None, founder_reserved: bool = False) -> WorkforceMember:
    row = db.query(WorkforceMember).filter_by(
        org_id=org_id, workspace_id=workspace_id, department_key=department_key
    ).one_or_none()
    if row is None:
        row = WorkforceMember(
            org_id=org_id, workspace_id=workspace_id, unit_id=unit_id,
            manager_member_id=manager_id, agent_id=agent_id, member_type=member_type,
            name=name, title=title, department_key=department_key,
            responsibilities=responsibilities, autonomy_level=autonomy,
            status="planned", is_founder_reserved=founder_reserved,
        )
        db.add(row)
        db.flush()
    else:
        row.unit_id = unit_id
        row.manager_member_id = manager_id
        if row.agent_id is None and agent_id is not None:
            row.agent_id = agent_id
    return row


def initialize_workforce(db: Session, *, org_id: str, workspace_id: str) -> dict:
    """Provision all 16 departments, functional groups, team units and position records.

    The function never activates an agent or grants a capability. It is safe to
    call repeatedly and preserves existing member/agent lifecycle state.
    """
    workspace = db.query(Workspace).filter_by(id=workspace_id, org_id=org_id).first()
    if workspace is None:
        raise ValueError("Workspace not found")

    office = _unit(
        db, org_id=org_id, workspace_id=workspace_id, parent_id=None,
        name="Office of the CEO", unit_type="office", department_key="office",
        description="Founder authority and executive coordination.",
    )

    founder = _member(
        db, org_id=org_id, workspace_id=workspace_id, unit_id=office.id,
        manager_id=None, member_type="human", name="Founder / CEO",
        title="Founder / Chief Executive Officer", department_key="office_founder",
        responsibilities=["Strategy and priorities", "Final commercial authority",
                          "Protected approvals", "Financial commitments", "Production releases"],
        autonomy=0, founder_reserved=True,
    )
    chief_agent = _agent(
        db, org_id=org_id, workspace_id=workspace_id,
        name="Chief of Staff / Claude Agency Supervisor", department="Office of the CEO",
        instructions=("Act as the founder's Chief of Staff. Convert founder objectives into evidence-backed plans; "
                      "coordinate group leads; identify dependencies, risks and decisions; request approval for "
                      "protected actions. Never claim authority to approve, send, spend, deploy or delete."),
    )
    chief = _member(
        db, org_id=org_id, workspace_id=workspace_id, unit_id=office.id,
        manager_id=founder.id, member_type="supervisor",
        name="Chief of Staff / Claude Agency Supervisor",
        title="Chief of Staff & Agency Supervisor", department_key="office_chief_of_staff",
        responsibilities=["Convert founder priorities into plans", "Coordinate department heads",
                          "Track dependencies, exceptions and execution", "Prepare founder decision briefs"],
        autonomy=2, agent_id=chief_agent.id,
    )
    assistant_agent = _agent(
        db, org_id=org_id, workspace_id=workspace_id, name="Executive Assistant",
        department="Office of the CEO",
        instructions="Prepare internal briefings, schedule proposals and reminders. Do not make external commitments.",
    )
    assistant = _member(
        db, org_id=org_id, workspace_id=workspace_id, unit_id=office.id,
        manager_id=chief.id, member_type="agent", name="Executive Assistant",
        title="Executive Assistant", department_key="office_executive_assistant",
        responsibilities=["Prepare briefs", "Coordinate internal scheduling", "Track reminders"],
        autonomy=1, agent_id=assistant_agent.id,
    )

    group_units: dict[str, WorkforceUnit] = {}
    group_heads: dict[str, WorkforceMember] = {}
    for group_key, (group_name, lead_title) in CATALOG_GROUPS.items():
        group_unit = _unit(
            db, org_id=org_id, workspace_id=workspace_id, parent_id=office.id,
            name=group_name, unit_type="group", department_key=group_key,
            description=f"{group_name} functional group.",
        )
        group_units[group_key] = group_unit
        group_agent = _agent(
            db, org_id=org_id, workspace_id=workspace_id, name=lead_title,
            department=group_name,
            instructions=f"Lead the {group_name} group. Coordinate its departments, surface risks and report material decisions to the Founder.",
        )
        group_heads[group_key] = _member(
            db, org_id=org_id, workspace_id=workspace_id, unit_id=group_unit.id,
            manager_id=founder.id, member_type="supervisor", name=lead_title,
            title=lead_title, department_key=group_key,
            responsibilities=[f"Coordinate {group_name} group", "Review department priorities",
                              "Escalate risk and resource conflicts to Founder"],
            autonomy=2, agent_id=group_agent.id,
        )

    department_units: dict[str, WorkforceUnit] = {}
    department_heads: dict[str, WorkforceMember] = {}
    specialist_members: dict[str, WorkforceMember] = {}
    team_units: dict[tuple[str, str], WorkforceUnit] = {}

    for key, name, group_key, description in DEPARTMENTS:
        unit = _unit(
            db, org_id=org_id, workspace_id=workspace_id, parent_id=group_units[group_key].id,
            name=name, unit_type="department", department_key=key, description=description,
        )
        department_units[key] = unit
        _, _, department_teams = DEPARTMENT_TEAMS[key]
        for team_key, (team_name, _) in department_teams.items():
            team_units[(key, team_key)] = _unit(
                db, org_id=org_id, workspace_id=workspace_id, parent_id=unit.id,
                name=team_name, unit_type="team", department_key=key,
                description=f"{team_name} team within {name}.",
            )

        head_title = HEAD_TITLES[key]
        head_agent = _agent(
            db, org_id=org_id, workspace_id=workspace_id, name=head_title,
            department=name,
            instructions=f"You are {head_title}. {HEAD_RESPONSIBILITIES[key][0]}. "
                          "Delegate only to direct reports with enabled capabilities. Escalate protected actions.",
        )
        head = _member(
            db, org_id=org_id, workspace_id=workspace_id, unit_id=unit.id,
            manager_id=group_heads[group_key].id, member_type="supervisor",
            name=head_title, title=head_title, department_key=f"{key}_head",
            responsibilities=HEAD_RESPONSIBILITIES[key], autonomy=2, agent_id=head_agent.id,
        )
        department_heads[key] = head

        specialist_name = f"{name} Specialist"
        specialist_agent = _agent(
            db, org_id=org_id, workspace_id=workspace_id, name=specialist_name,
            department=name,
            instructions=f"Department specialist for {name}. {description} Produce evidence-backed recommendations and escalate approval-required actions.",
        )
        specialist_members[key] = _member(
            db, org_id=org_id, workspace_id=workspace_id, unit_id=unit.id,
            manager_id=head.id, member_type="agent", name=specialist_name,
            title=specialist_name, department_key=key,
            responsibilities=[description, "Produce evidence-backed recommendations",
                              "Escalate approval-required actions"],
            autonomy=1, agent_id=specialist_agent.id,
        )

    member_by_position = {
        "office_founder": founder,
        "office_chief_of_staff": chief,
        "office_executive_assistant": assistant,
    }
    for group_key, member in group_heads.items():
        member_by_position[key_for("group", group_key)] = member
    for dept_key, member in department_heads.items():
        member_by_position[key_for("dept", dept_key, "head")] = member

    position_count = 0
    for position_key, department_key, title, team_key, reports_to_key, autonomy, responsibilities in build_positions():
        if department_key == "Office of the CEO":
            unit_id, group_key, team_unit_id = office.id, "office", None
        elif department_key in CATALOG_GROUPS:
            unit_id, group_key, team_unit_id = group_units[department_key].id, department_key, None
        else:
            unit_id = department_units[department_key].id
            group_key = next(row[2] for row in DEPARTMENTS if row[0] == department_key)
            team_unit_id = team_units[(department_key, team_key)].id if (department_key, team_key) in team_units else None

        assigned = member_by_position.get(position_key)
        row = db.query(WorkforcePosition).filter_by(
            org_id=org_id, workspace_id=workspace_id, position_key=position_key
        ).one_or_none()
        if row is None:
            row = WorkforcePosition(
                org_id=org_id, workspace_id=workspace_id, unit_id=unit_id,
                team_unit_id=team_unit_id, assigned_member_id=assigned.id if assigned else None,
                position_key=position_key, title=title, department_key=department_key,
                group_key=group_key, team_key=team_key, reports_to_position_key=reports_to_key,
                responsibilities=responsibilities, autonomy_ceiling=autonomy, status="planned",
            )
            db.add(row)
        else:
            row.unit_id, row.team_unit_id = unit_id, team_unit_id
            row.reports_to_position_key = reports_to_key
            if row.assigned_member_id is None and assigned is not None:
                row.assigned_member_id = assigned.id
        position_count += 1

    db.flush()
    return {
        "office_units": 1,
        "functional_groups": len(CATALOG_GROUPS),
        "departments": len(DEPARTMENTS),
        "teams": len(team_units),
        "group_heads": len(group_heads),
        "department_heads": len(department_heads),
        "specialists": len(specialist_members),
        "positions": position_count,
        "founder_reserved": 1,
    }
