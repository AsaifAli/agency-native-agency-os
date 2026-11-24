from app.skills_registry import SkillCatalogError, get_skill, list_skills


def test_skill_catalog_is_curated_disabled_and_tool_free():
    skills = list_skills()
    assert len(skills) == 18
    assert len({skill["name"] for skill in skills}) == len(skills)
    for skill in skills:
        assert skill["review_status"] == "reviewed"
        assert skill["enabled"] is False
        assert skill["allowed_tools"] == []
        assert set(skill["allowed_data_classes"]) <= {"public", "synthetic"}
        assert len(skill["content_sha256"]) == 64
        assert "content" not in skill


def test_skill_catalog_filters_by_category_and_query():
    engineering = list_skills(category="engineering")
    assert engineering
    assert all(skill["category"] == "engineering" for skill in engineering)

    matches = list_skills(query="red-green-refactor")
    assert [skill["name"] for skill in matches] == ["test-driven-development"]


def test_skill_detail_returns_frontmatter_and_pinned_provenance():
    skill = get_skill("test-driven-development")
    assert "name: test-driven-development" in skill["content"]
    assert skill["sources"]
    assert all(source["revision"] for source in skill["sources"])
    assert skill["enabled"] is False
    assert skill["allowed_tools"] == []


def test_unknown_skill_is_not_found():
    try:
        get_skill("not-a-real-skill")
    except KeyError:
        pass
    else:
        raise AssertionError("Unknown skills must not be served")


def test_invalid_catalog_fails_closed(monkeypatch, tmp_path):
    import app.skills_registry as registry

    bad_catalog = tmp_path / "catalog.json"
    bad_catalog.write_text('{"schema_version": 99, "sources": {}, "skills": []}', encoding="utf-8")
    monkeypatch.setattr(registry, "CATALOG_PATH", bad_catalog)
    try:
        registry.list_skills()
    except SkillCatalogError:
        pass
    else:
        raise AssertionError("Unsupported catalog schema must fail closed")


def test_department_charters_reference_known_skills_without_granting_permissions():
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    catalog_names = {skill["name"] for skill in list_skills()}
    charters = sorted((root / "agents" / "departments").glob("*.md"))
    charters = [path for path in charters if path.name != "README.md"]
    assert len(charters) == 16

    for charter in charters:
        content = charter.read_text(encoding="utf-8")
        assert "Select reviewed skill IDs from" not in content
        referenced = set(re.findall(r"\]\(\.\./\.\./skills/([a-z0-9-]+)/SKILL\.md\)", content))
        assert referenced
        assert referenced <= catalog_names
        assert "does not enable a workforce member or grant a tool" in content or "Recommendations only" in content
