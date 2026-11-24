from app.evaluation.metrics import citation_completeness, citation_correctness, recall_at_k


def test_citation_completeness_handles_one_shot_iterables():
    citations = (value for value in ["source-a", "source-b"])
    required = (value for value in ["source-a", "source-b"])
    assert citation_completeness(citations, required) == 1.0


def test_citation_completeness_detects_missing_sources():
    assert citation_completeness(["source-a"], ["source-a", "source-b"]) == 0.5


def test_citation_correctness_rejects_irrelevant_citations():
    assert citation_correctness(["source-a", "unknown"], ["source-a"]) == 0.5


def test_recall_at_k_empty_relevance_is_neutral():
    assert recall_at_k(["anything"], [], 5) == 1.0
