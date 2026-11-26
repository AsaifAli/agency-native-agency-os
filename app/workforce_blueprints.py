"""Curated specialist profiles and versioned team blueprints.

Definitions are declarative planning metadata only. They never grant tools,
activate agents, bypass approvals, or start executions.
"""
from __future__ import annotations

SCHEMA_VERSION = 1
CATALOG_VERSION = "2026.11.26"


SPECIALISTS = [
    {
        "specialist_key": "multi_agent_architect",
        "title": "Multi-Agent Systems Architect",
        "department_key": "solutions_consulting_strategy",
        "mission": "Design bounded agent workflows, delegation contracts and failure handling.",
        "responsibilities": ["Choose the simplest suitable orchestration pattern", "Define typed inputs and outputs for each handoff", "Bound fan-out, chain depth, context, iterations, time and cost", "Define partial-result and escalation behavior"],
        "inputs": ["objective", "constraints", "available_specialists", "runtime_capabilities"],
        "outputs": ["workflow_design", "delegation_contracts", "failure_policy", "evaluation_requirements"],
        "not_responsible_for": ["Granting tools or permissions", "Approving protected actions", "Executing production changes"],
        "review_gate": "Independent architecture review before a workflow is activated",
    },
    {
        "specialist_key": "ai_solutions_architect",
        "title": "AI Solutions Architect",
        "department_key": "solutions_consulting_strategy",
        "mission": "Translate discovery evidence into feasible, scoped AI solution designs.",
        "responsibilities": ["Map current and target processes", "Document requirements and assumptions", "Compare solution options and risks", "Define acceptance criteria and handoff to engineering"],
        "inputs": ["discovery_notes", "business_objectives", "constraints", "existing_systems"],
        "outputs": ["requirements_register", "solution_architecture", "assumptions", "acceptance_criteria"],
        "not_responsible_for": ["Committing pricing or delivery dates", "Approving contracts", "Marking own implementation as independently verified"],
        "review_gate": "Founder approval for commercial commitments; engineering and QA review for implementation",
    },
    {
        "specialist_key": "backend_architect",
        "title": "Backend Architect",
        "department_key": "ai_engineering_development",
        "mission": "Design maintainable APIs, data boundaries and backend service contracts.",
        "responsibilities": ["Define module and API boundaries", "Specify validation and error contracts", "Design idempotent state transitions", "Document migrations and rollback considerations"],
        "inputs": ["requirements_register", "architecture_constraints", "existing_api_contracts"],
        "outputs": ["api_contract", "data_model", "implementation_plan", "migration_plan"],
        "not_responsible_for": ["Changing production permissions without approval", "Handling secrets in prompts or logs", "Self-approving security-sensitive changes"],
        "review_gate": "Engineering review plus security review for identity, tenant or permission changes",
    },
    {
        "specialist_key": "database_reliability_engineer",
        "title": "Database Reliability Engineer",
        "department_key": "infrastructure_it_operations",
        "mission": "Protect database integrity, recoverability and operational reliability.",
        "responsibilities": ["Review schema and migration safety", "Verify indexes and query behavior", "Design backup and restore tests", "Define RPO, RTO and recovery evidence"],
        "inputs": ["schema", "migration_plan", "workload_profile", "recovery_objectives"],
        "outputs": ["database_review", "migration_risks", "restore_test_plan", "reliability_findings"],
        "not_responsible_for": ["Running destructive migrations without approval", "Claiming backup success without restore evidence"],
        "review_gate": "Independent migration review and demonstrated restore test for release-critical changes",
    },
    {
        "specialist_key": "ai_engineer",
        "title": "AI Engineer",
        "department_key": "ai_engineering_development",
        "mission": "Implement bounded AI, retrieval and agent capabilities against approved contracts.",
        "responsibilities": ["Implement model and tool adapters", "Keep deterministic work in code", "Add evaluation and regression tests", "Record model and prompt versions"],
        "inputs": ["solution_architecture", "api_contract", "approved_data_policy", "evaluation_requirements"],
        "outputs": ["implementation", "tests", "model_configuration", "technical_notes"],
        "not_responsible_for": ["Selecting unauthorized data or runtimes", "Changing tool grants", "Approving own release"],
        "review_gate": "Engineering code review and independent evaluation",
    },
    {
        "specialist_key": "ai_code_security_auditor",
        "title": "AI-Generated Code Security Auditor",
        "department_key": "quality_assurance_security",
        "mission": "Identify exploitable code, identity, data and model-boundary risks with reproducible evidence.",
        "responsibilities": ["Inspect secret exposure and credential handling", "Test tenant isolation and authorization boundaries", "Review prompt and tool injection surfaces", "Require rescan evidence for claimed fixes"],
        "inputs": ["code_changes", "threat_model", "security_test_results", "data_flow_inventory"],
        "outputs": ["findings", "reproduction_steps", "severity", "remediation", "rescan_evidence"],
        "not_responsible_for": ["Declaring compliance from checklist completion", "Rotating provider secrets without authorization", "Suppressing uncertain findings"],
        "review_gate": "Critical findings block release pending independent verification",
    },
    {
        "specialist_key": "privacy_engineer",
        "title": "Privacy Engineer",
        "department_key": "legal_risk_compliance",
        "mission": "Make data minimization, purpose, retention and deletion enforceable across data flows.",
        "responsibilities": ["Map personal-data stores and flows", "Review purpose and data-classification controls", "Verify consent and suppression enforcement", "Test retention and deletion propagation"],
        "inputs": ["data_flow_inventory", "client_policy", "retention_schedule", "processing_purposes"],
        "outputs": ["privacy_assessment", "data_minimization_actions", "retention_tests", "deletion_evidence"],
        "not_responsible_for": ["Providing legal advice", "Declaring data anonymous without evidence", "Approving new third-party data transfers"],
        "review_gate": "Privacy and legal review before new sensitive data flows",
    },
    {
        "specialist_key": "ui_finish_gate_reviewer",
        "title": "UI Finish-Gate Reviewer",
        "department_key": "quality_assurance_security",
        "mission": "Verify that interfaces serve their actual workflow and handle all critical states.",
        "responsibilities": ["Review desktop and mobile behavior", "Check accessibility, focus and keyboard flows", "Verify loading, empty, error and success states", "Record visual and functional evidence"],
        "inputs": ["product_lens", "design_constraints", "screenshots", "browser_test_results"],
        "outputs": ["ui_review", "findings", "responsive_evidence", "pass_or_hold"],
        "not_responsible_for": ["Redesigning to follow trends", "Changing brand constraints without approval", "Passing screens without evidence"],
        "review_gate": "PASS only with evidence; HOLD when critical workflow or accessibility issues remain",
    },
    {
        "specialist_key": "discovery_coach",
        "title": "Business Discovery Coach",
        "department_key": "business_development_sales",
        "mission": "Structure client discovery and surface measurable business problems and decision criteria.",
        "responsibilities": ["Prepare discovery questions", "Separate facts, assumptions and unknowns", "Capture current-state workflow and pain points", "Identify stakeholders and measurable outcomes"],
        "inputs": ["lead_context", "meeting_notes", "industry_context"],
        "outputs": ["discovery_brief", "pain_points", "success_metrics", "open_questions"],
        "not_responsible_for": ["Inventing client facts", "Making pricing or scope commitments", "Sending external messages without authorization"],
        "review_gate": "Human review before client-facing commitments or proposal use",
    },
    {
        "specialist_key": "content_strategist",
        "title": "Content Strategist",
        "department_key": "marketing_brand",
        "mission": "Develop evidence-backed channel-specific content aligned to approved positioning.",
        "responsibilities": ["Define audience and content angle", "Prepare channel-specific drafts", "Preserve source provenance", "Flag unsupported claims and review needs"],
        "inputs": ["approved_positioning", "campaign_brief", "source_material"],
        "outputs": ["content_plan", "channel_drafts", "source_notes", "review_flags"],
        "not_responsible_for": ["Publishing content", "Making unsupported performance claims", "Changing approved positioning"],
        "review_gate": "Every channel draft requires individual human approval before publication",
    },
]


BLUEPRINTS = [
    {
        "slug": "client_onboarding_delivery",
        "title": "Client Onboarding & Delivery",
        "summary": "Move an approved engagement from discovery handoff through solution design, implementation, independent QA and handover.",
        "duration_hint": "Project-scoped",
        "groups": [
            {"group": "Discovery and solution design", "activation": "always", "tasks": [
                {"specialist_key": "discovery_coach", "department_key": "business_development_sales", "title": "Validate discovery brief", "objective": "Turn verified discovery evidence into a clear problem statement, stakeholders and success measures.", "inputs": ["lead_context", "meeting_notes"], "outputs": ["discovery_brief", "success_metrics"], "review_required": True},
                {"specialist_key": "ai_solutions_architect", "department_key": "solutions_consulting_strategy", "title": "Design the solution", "objective": "Produce requirements, assumptions, architecture options and acceptance criteria.", "inputs": ["discovery_brief", "success_metrics"], "outputs": ["requirements_register", "solution_architecture", "acceptance_criteria"], "review_required": True},
            ]},
            {"group": "Implementation", "activation": "phase", "tasks": [
                {"specialist_key": "backend_architect", "department_key": "ai_engineering_development", "title": "Define implementation contracts", "objective": "Specify API, data and migration boundaries before implementation.", "inputs": ["solution_architecture", "acceptance_criteria"], "outputs": ["api_contract", "data_model", "migration_plan"], "review_required": True},
                {"specialist_key": "ai_engineer", "department_key": "ai_engineering_development", "title": "Implement approved solution", "objective": "Implement against approved contracts with tests and versioned model configuration.", "inputs": ["api_contract", "approved_data_policy"], "outputs": ["implementation", "tests", "technical_notes"], "review_required": True},
            ]},
            {"group": "Independent verification and handover", "activation": "post_fix", "tasks": [
                {"specialist_key": "ai_code_security_auditor", "department_key": "quality_assurance_security", "title": "Review security and tenant boundaries", "objective": "Test security-sensitive changes and produce reproducible findings and rescan evidence.", "inputs": ["code_changes", "threat_model"], "outputs": ["findings", "rescan_evidence"], "review_required": True},
                {"specialist_key": "ui_finish_gate_reviewer", "department_key": "quality_assurance_security", "title": "Verify interface finish gate", "objective": "Review workflow usability, responsive behavior and critical UI states.", "inputs": ["product_lens", "browser_test_results"], "outputs": ["ui_review", "pass_or_hold"], "review_required": True},
            ]},
        ],
    },
    {
        "slug": "enterprise_feature_delivery",
        "title": "Enterprise Feature Delivery",
        "summary": "Deliver a bounded enterprise feature with architecture, privacy, reliability, security and independent release evidence.",
        "duration_hint": "Milestone-based",
        "groups": [
            {"group": "Architecture and risk", "activation": "always", "tasks": [
                {"specialist_key": "multi_agent_architect", "department_key": "solutions_consulting_strategy", "title": "Define orchestration and handoff contracts", "objective": "Select bounded collaboration patterns and define structured delegation and failure contracts.", "inputs": ["objective", "constraints"], "outputs": ["workflow_design", "delegation_contracts"], "review_required": True},
                {"specialist_key": "backend_architect", "department_key": "ai_engineering_development", "title": "Define API and data contracts", "objective": "Specify stable interfaces, validation, idempotency and migration boundaries.", "inputs": ["requirements_register"], "outputs": ["api_contract", "data_model"], "review_required": True},
                {"specialist_key": "privacy_engineer", "department_key": "legal_risk_compliance", "title": "Assess data flows", "objective": "Review minimization, purpose, classification, retention and deletion requirements.", "inputs": ["data_flow_inventory", "client_policy"], "outputs": ["privacy_assessment", "retention_tests"], "review_required": True},
            ]},
            {"group": "Build and verification", "activation": "phase", "tasks": [
                {"specialist_key": "ai_engineer", "department_key": "ai_engineering_development", "title": "Implement feature", "objective": "Implement the approved design with regression and evaluation coverage.", "inputs": ["api_contract", "approved_data_policy"], "outputs": ["implementation", "tests"], "review_required": True},
                {"specialist_key": "database_reliability_engineer", "department_key": "infrastructure_it_operations", "title": "Review database reliability", "objective": "Review migration safety, operational behavior and recovery evidence.", "inputs": ["schema", "migration_plan"], "outputs": ["database_review", "restore_test_plan"], "review_required": True},
                {"specialist_key": "ai_code_security_auditor", "department_key": "quality_assurance_security", "title": "Run independent security review", "objective": "Verify authorization, tenant isolation, secret handling and model boundaries.", "inputs": ["code_changes", "threat_model"], "outputs": ["findings", "reproduction_steps"], "review_required": True},
            ]},
        ],
    },
    {
        "slug": "marketing_campaign",
        "title": "Evidence-Backed Marketing Campaign",
        "summary": "Prepare coordinated channel drafts and measurement plans; publishing remains a separate approved action.",
        "duration_hint": "Campaign-scoped",
        "groups": [
            {"group": "Strategy and drafts", "activation": "always", "tasks": [
                {"specialist_key": "content_strategist", "department_key": "marketing_brand", "title": "Prepare channel content plan", "objective": "Create channel-specific drafts grounded in approved positioning and source material.", "inputs": ["approved_positioning", "campaign_brief", "source_material"], "outputs": ["content_plan", "channel_drafts"], "review_required": True},
                {"specialist_key": "discovery_coach", "department_key": "business_development_sales", "title": "Align content with buyer questions", "objective": "Identify customer questions and measurable outcomes from verified discovery evidence.", "inputs": ["lead_context", "meeting_notes"], "outputs": ["pain_points", "success_metrics"], "review_required": True},
            ]},
            {"group": "Review and measurement", "activation": "phase", "tasks": [
                {"specialist_key": "ui_finish_gate_reviewer", "department_key": "quality_assurance_security", "title": "Review campaign landing experience", "objective": "Check conversion workflow, accessibility and responsive states.", "inputs": ["product_lens", "browser_test_results"], "outputs": ["ui_review", "pass_or_hold"], "review_required": True},
            ]},
        ],
    },
    {
        "slug": "incident_response",
        "title": "Incident Response and Recovery",
        "summary": "Coordinate bounded diagnosis, safe remediation, independent verification and post-incident learning.",
        "duration_hint": "Incident-scoped",
        "groups": [
            {"group": "Triage and containment", "activation": "always", "tasks": [
                {"specialist_key": "multi_agent_architect", "department_key": "solutions_consulting_strategy", "title": "Coordinate incident workstreams", "objective": "Split independent diagnostic work and define a bounded synthesis and escalation plan.", "inputs": ["incident_summary", "constraints"], "outputs": ["workstream_plan", "failure_policy"], "review_required": True},
                {"specialist_key": "database_reliability_engineer", "department_key": "infrastructure_it_operations", "title": "Assess database impact and recovery", "objective": "Assess database integrity, recovery options and evidence required before changes.", "inputs": ["incident_summary", "database_health"], "outputs": ["database_review", "recovery_plan"], "review_required": True},
            ]},
            {"group": "Remediation verification", "activation": "post_fix", "tasks": [
                {"specialist_key": "ai_code_security_auditor", "department_key": "quality_assurance_security", "title": "Verify security remediation", "objective": "Reproduce the finding and verify the fix with a rescan.", "inputs": ["incident_findings", "code_changes"], "outputs": ["reproduction_steps", "rescan_evidence"], "review_required": True},
                {"specialist_key": "ui_finish_gate_reviewer", "department_key": "quality_assurance_security", "title": "Verify user-facing recovery", "objective": "Verify user-visible error recovery and critical workflow states.", "inputs": ["product_lens", "browser_test_results"], "outputs": ["ui_review", "pass_or_hold"], "review_required": True},
            ]},
        ],
    },
]


def validate_catalog() -> None:
    specialist_ids = [item["specialist_key"] for item in SPECIALISTS]
    if len(specialist_ids) != len(set(specialist_ids)):
        raise ValueError("Duplicate specialist key")
    specialist_map = {item["specialist_key"]: item for item in SPECIALISTS}
    slugs = [item["slug"] for item in BLUEPRINTS]
    if len(slugs) != len(set(slugs)):
        raise ValueError("Duplicate blueprint slug")
    allowed_activation = {"always", "phase", "as_needed", "post_fix"}
    for blueprint in BLUEPRINTS:
        for group in blueprint["groups"]:
            if group["activation"] not in allowed_activation:
                raise ValueError("Unsupported blueprint activation")
            for task in group["tasks"]:
                specialist = specialist_map.get(task["specialist_key"])
                if specialist is None or specialist["department_key"] != task["department_key"]:
                    raise ValueError("Blueprint task references an invalid specialist or department")
                if task["review_required"] is not True:
                    raise ValueError("Blueprint tasks must require review")
    for specialist in SPECIALISTS:
        if specialist.get("default_enabled", False) is not False:
            raise ValueError("Specialists must remain disabled by default")
        if specialist.get("tool_grants", []) != []:
            raise ValueError("Specialist definitions cannot grant tools")


def list_specialists() -> dict:
    validate_catalog()
    return {"schema_version": SCHEMA_VERSION, "catalog_version": CATALOG_VERSION,
            "specialists": [dict(item, default_enabled=False, tool_grants=[]) for item in SPECIALISTS]}


def list_blueprints() -> dict:
    validate_catalog()
    return {"schema_version": SCHEMA_VERSION, "catalog_version": CATALOG_VERSION,
            "blueprints": [dict(item) for item in BLUEPRINTS]}
