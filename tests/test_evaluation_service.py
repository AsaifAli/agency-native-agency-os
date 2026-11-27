from app.evaluation_service import catalog, evaluate


def test_registry_exposes_only_agency_os_packs():
    names = {item["name"] for item in catalog()}
    assert names == {
    "agent_workflow",
    "rag",
    "safety_security",
    "regression",
}


def test_agent_workflow_gate_fails_when_approval_compliance_fails():
    result = evaluate(
        "agent_workflow",
        {"required_steps": ["plan", "execute"]},
        {
            "status": "completed",
            "completed_steps": ["plan", "execute"],
            "tool_call_validity": 1.0,
            "policy_pass_rate": 1.0,
            "approval_compliant": False,
            "execution_reliability": 1.0,
            "fallback_rate": 0.0,
        },
    )
    assert result["score"] > 0.8
    assert result["passed"] is False
    assert result["gate_results"]["approval_compliance"]["passed"] is False


def test_rag_pack_calculates_retrieval_and_citation_gates():
    result = evaluate(
        "rag",
        {"relevant_documents": ["a", "b"], "required_citations": ["src-1"], "relevant_citations": ["src-1"]},
        {
            "retrieved_documents": ["a", "b"],
            "citations": ["src-1"],
            "answer_relevance": 1.0,
            "groundedness": 1.0,
        },
    )
    assert result["passed"] is True
    assert result["metrics"]["recall@5"] == 1.0
