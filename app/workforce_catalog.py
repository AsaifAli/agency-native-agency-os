"""Canonical position and team catalogue for the full agency org chart.

Positions are durable responsibilities; they are not automatically running agents.
The seed routine creates only a small set of linked Agent definitions and leaves
all of them disabled until a founder deliberately enables them.
"""
import re

GROUPS = {
    "growth": ("Growth", "Head of Growth"),
    "strategy_commercial": ("Strategy & Commercial", "Head of Strategy & Commercial"),
    "technology": ("Technology & Innovation", "Head of Technology & Innovation"),
    "delivery_quality": ("Execution & Quality", "Head of Execution & Quality"),
    "business_operations": ("Business Operations & Relationships", "Head of Business Operations & Relationships"),
}

# Department key -> (department name, group key, team -> positions)
DEPARTMENT_TEAMS = {
    "marketing_brand": ("Marketing & Brand", "growth", {
        "brand_content": ("Brand & Content", ["Brand Strategist", "Content Strategist", "Content Specialist"]),
        "growth_channels": ("Growth Channels & Analytics", ["SEO Specialist", "Social Media Manager", "Growth Marketing Specialist", "Marketing Analyst"]),
    }),
    "business_development_sales": ("Business Development & Sales", "growth", {
        "lead_generation": ("Lead Generation & Prospecting", ["Lead Generation Specialist", "Lead Research Analyst", "Sales Development Representative"]),
        "sales_accounts": ("Sales & Account Management", ["Business Development Executive", "Account Executive", "CRM Manager", "Proposal Specialist"]),
    }),
    "market_research_intelligence": ("Market Research & Intelligence", "growth", {
        "market_intelligence": ("Market & Competitor Intelligence", ["Industry Research Analyst", "Competitor Intelligence Analyst", "Technology Market Analyst", "Opportunity Analyst", "Research Quality Reviewer"]),
    }),
    "solutions_consulting_strategy": ("Solutions Consulting & Strategy", "strategy_commercial", {
        "discovery_architecture": ("Discovery & Architecture", ["Business Analyst", "AI Solutions Architect", "Automation Consultant", "Data Solutions Consultant"]),
        "presales_proposals": ("Presales & Proposals", ["Presales Consultant", "Proposal Architect"]),
    }),
    "finance_accounts": ("Finance & Accounts", "strategy_commercial", {
        "financial_control": ("Financial Control & Analysis", ["Accountant", "Financial Analyst", "Budget Analyst", "Revenue Analyst"]),
        "receivables_payables": ("Receivables & Payables", ["Accounts Receivable Specialist", "Accounts Payable Specialist"]),
    }),
    "legal_risk_compliance": ("Legal, Risk & Compliance", "strategy_commercial", {
        "contracts_privacy": ("Contracts, Privacy & Compliance", ["Contract Analyst", "Privacy Analyst", "Compliance Analyst"]),
        "risk_ip": ("Risk & Intellectual Property", ["IP & Licensing Analyst", "Risk Analyst"]),
    }),
    "ai_research_innovation": ("AI Research & Innovation", "technology", {
        "llm_agent_research": ("LLM & Agent Research", ["LLM Research Specialist", "Agentic AI Researcher", "RAG Research Specialist"]),
        "applied_ai_evaluation": ("Applied AI & Evaluation", ["Computer Vision Researcher", "Speech AI Researcher", "Evaluation Researcher"]),
    }),
    "ai_engineering_development": ("AI Engineering & Development", "technology", {
        "ai_llm_engineering": ("AI, LLM & Agent Engineering", ["AI Engineer", "LLM Engineer", "Agentic AI Engineer", "RAG Engineer", "ML Engineer"]),
        "product_data_engineering": ("Product & Data Engineering", ["Backend Engineer", "Frontend Engineer", "Data Engineer"]),
    }),
    "automation_integration_engineering": ("Automation & Integration Engineering", "technology", {
        "workflow_integration": ("Workflow & Integration Engineering", ["Workflow Automation Engineer", "Integration Engineer", "Process Automation Analyst"]),
        "mcp_voice_quality": ("MCP, Voice & Automation QA", ["MCP Engineer", "Voice Automation Engineer", "Automation QA Specialist"]),
    }),
    "infrastructure_it_operations": ("Infrastructure & IT Operations", "technology", {
        "platform_reliability": ("Platform & Reliability", ["Cloud/DevOps Engineer", "Platform Engineer", "Database Administrator", "Site Reliability Engineer"]),
        "it_security_support": ("IT, Security & Support", ["Security Operations Analyst", "IT Support Specialist"]),
    }),
    "pmo": ("Project Management Office", "delivery_quality", {
        "project_controls": ("Project Controls & Reporting", ["Project Manager", "Project Coordinator", "Resource Planner", "Risk & Dependency Analyst", "Project Reporting Analyst"]),
    }),
    "delivery_implementation": ("Delivery & Implementation", "delivery_quality", {
        "implementation_deployment": ("Implementation & Deployment", ["Implementation Manager", "Technical Implementation Specialist", "Deployment Engineer", "Data Migration Specialist"]),
        "documentation_handover": ("Documentation & Handover", ["Documentation Specialist", "Handover Specialist"]),
    }),
    "quality_assurance_security": ("Quality Assurance & Security", "delivery_quality", {
        "testing_evaluation": ("Software Testing & AI Evaluation", ["Software QA Engineer", "Automation Test Engineer", "AI Evaluation Engineer", "Performance Tester"]),
        "security_release": ("Security & Release Assurance", ["AppSec Analyst", "Data Security Analyst", "Release Quality Reviewer"]),
    }),
    "client_success_support": ("Client Success & Support", "business_operations", {
        "onboarding_support": ("Onboarding & Support", ["Customer Success Manager", "Onboarding Specialist", "Support Specialist", "Technical Support Engineer"]),
        "feedback_growth": ("Feedback & Account Growth", ["Feedback Analyst", "Account Growth Specialist"]),
    }),
    "hr_people_operations": ("HR & People Operations", "business_operations", {
        "talent_people_ops": ("Talent & People Operations", ["Talent Acquisition Specialist", "HR Operations Specialist", "Performance Analyst"]),
        "learning_workforce": ("Learning & Workforce Planning", ["Learning & Development Specialist", "Workforce Planning Analyst", "Culture & Engagement Specialist"]),
    }),
    "administration_procurement": ("Administration & Procurement", "business_operations", {
        "procurement_vendor": ("Procurement & Vendor Management", ["Procurement Specialist", "Vendor Management Analyst", "Subscription Manager"]),
        "assets_administration": ("Assets & Administration", ["Asset Management Specialist", "Administrative Assistant"]),
    }),
}

HEAD_TITLES = {
    "marketing_brand": "Head of Marketing",
    "business_development_sales": "Head of Business Development",
    "market_research_intelligence": "Research Director",
    "solutions_consulting_strategy": "Head of Solutions",
    "finance_accounts": "Finance Controller",
    "legal_risk_compliance": "Legal & Compliance Lead",
    "ai_research_innovation": "Head of AI Research",
    "ai_engineering_development": "Head of AI Engineering",
    "automation_integration_engineering": "Head of Automation",
    "infrastructure_it_operations": "IT Operations Lead",
    "pmo": "Head of PMO",
    "delivery_implementation": "Head of Delivery",
    "quality_assurance_security": "Head of QA & Security",
    "client_success_support": "Head of Client Success",
    "hr_people_operations": "Head of HR",
    "administration_procurement": "Administration Manager",
}

HEAD_RESPONSIBILITIES = {
    "marketing_brand": ["Own brand positioning, content, SEO, campaigns and channel analytics"],
    "business_development_sales": ["Own lead generation, qualification, CRM, pipeline and proposal coordination"],
    "market_research_intelligence": ["Own sourced market, competitor, technology and opportunity intelligence"],
    "solutions_consulting_strategy": ["Own discovery, feasibility, solution architecture and presales"],
    "finance_accounts": ["Own management finance, budgets, receivables and project margin visibility"],
    "legal_risk_compliance": ["Own contract review coordination, privacy, licensing and risk escalation"],
    "ai_research_innovation": ["Own model, agent, RAG, vision, speech and evaluation research"],
    "ai_engineering_development": ["Own engineering implementation, APIs, applications, data and model integration"],
    "automation_integration_engineering": ["Own integrations, workflow adapters, MCP and voice automation"],
    "infrastructure_it_operations": ["Own environments, platform, databases, reliability, security operations and IT"],
    "pmo": ["Own plans, milestones, dependencies, resource coordination and status reporting"],
    "delivery_implementation": ["Own implementation, deployment coordination, migration and handover"],
    "quality_assurance_security": ["Independently verify requirements, software quality, AI evaluation and security"],
    "client_success_support": ["Own client relationship, onboarding, support, feedback and account health"],
    "hr_people_operations": ["Own role design, talent, people operations, learning and workforce planning"],
    "administration_procurement": ["Own procurement, vendors, subscriptions, assets and administration"],
}

def key_for(*parts: str) -> str:
    raw = "_".join(parts).lower()
    return re.sub(r"[^a-z0-9]+", "_", raw).strip("_")

def build_positions():
    rows = [
        ("office_founder", "Office of the CEO", "Founder / Chief Executive Officer", "office", "office_chief_of_staff", 0,
         ["Strategy, final authority, protected approvals, financial commitments and risk appetite"]),
        ("office_chief_of_staff", "Office of the CEO", "Chief of Staff / Claude Agency Supervisor", "office", "office_founder", 2,
         ["Convert founder priorities into plans", "Coordinate group and department heads", "Track cross-group dependencies", "Escalate exceptions and prepare decision briefs"]),
        ("office_executive_assistant", "Office of the CEO", "Executive Assistant", "office", "office_chief_of_staff", 1,
         ["Prepare briefings", "Coordinate internal scheduling", "Track reminders and meeting administration"]),
    ]
    for dept_key, (dept_name, group_key, teams) in DEPARTMENT_TEAMS.items():
        group_head_key = key_for("group", group_key)
        head_title = HEAD_TITLES[dept_key]
        rows.append((key_for("dept", dept_key, "head"), dept_key, head_title, "department", group_head_key, 2,
                     HEAD_RESPONSIBILITIES[dept_key]))
        for team_key, (team_name, titles) in teams.items():
            for title in titles:
                rows.append((key_for(dept_key, title), dept_key, title, team_key,
                             key_for("dept", dept_key, "head"), 1,
                             [f"Perform {title.lower()} responsibilities for {dept_name}"]))
    for group_key, (group_name, lead_title) in GROUPS.items():
        rows.append((key_for("group", group_key), group_key, lead_title, "group",
                     "office_founder", 2, [f"Coordinate {group_name} group and report material risks to Founder"]))
    return rows
