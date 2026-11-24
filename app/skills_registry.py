"""Read-only, fail-closed registry for reviewed Agent Skills assets."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

SKILLS_ROOT = Path(__file__).resolve().parent.parent / "skills"
CATALOG_PATH = SKILLS_ROOT / "catalog.json"
_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_FRONTMATTER_RE = re.compile(r"\A---\s*\n(?P<header>.*?)\n---\s*\n", re.DOTALL)
_DESCRIPTION_RE = re.compile(r'^description:\s*(?:"(?P<quoted>[^"]+)"|(?P<plain>.+?))\s*$', re.MULTILINE)
_SKILL_NAME_RE = re.compile(r"^name:\s*(?P<name>[a-z0-9-]+)\s*$", re.MULTILINE)


class SkillCatalogError(ValueError):
    """The checked-in skill catalog or a skill asset is invalid."""


class SkillNotFound(KeyError):
    """No reviewed skill exists with the requested name."""


def _load_manifest() -> dict[str, Any]:
    try:
        manifest = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SkillCatalogError("Skill catalog is unavailable or invalid") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise SkillCatalogError("Unsupported skill catalog schema version")
    if not isinstance(manifest.get("sources"), dict) or not isinstance(manifest.get("skills"), list):
        raise SkillCatalogError("Skill catalog must define sources and skills")
    for source_id, source in manifest["sources"].items():
        if not isinstance(source_id, str) or not isinstance(source, dict):
            raise SkillCatalogError("Skill source entries must be named objects")
        if not all(isinstance(source.get(field), str) and source[field].strip()
                   for field in ("repository", "revision", "license", "use")):
            raise SkillCatalogError(f"Skill source metadata is incomplete: {source_id}")
    return manifest


def _read_entry(entry: dict[str, Any], sources: dict[str, Any]) -> dict[str, Any]:
    name = entry.get("name")
    relative_path = entry.get("path")
    if not isinstance(entry, dict):
        raise SkillCatalogError("Skill entries must be objects")
    if not isinstance(name, str) or not _NAME_RE.fullmatch(name):
        raise SkillCatalogError("Skill name is invalid")
    if not isinstance(entry.get("description"), str) or not entry["description"].strip():
        raise SkillCatalogError(f"Skill description is invalid: {name}")
    if not isinstance(entry.get("category"), str) or not entry["category"].strip():
        raise SkillCatalogError(f"Skill category is invalid: {name}")
    if relative_path != f"{name}/SKILL.md":
        raise SkillCatalogError(f"Skill path must be the standard directory path: {name}")
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise SkillCatalogError(f"Unsafe skill path: {name}")
    root = SKILLS_ROOT.resolve()
    target = (root / path).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise SkillCatalogError(f"Skill path escapes the catalog root: {name}") from exc

    try:
        content = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise SkillCatalogError(f"Skill asset is missing: {name}") from exc
    match = _FRONTMATTER_RE.match(content)
    if not match:
        raise SkillCatalogError(f"Skill frontmatter is missing: {name}")
    header = match.group("header")
    name_match = _SKILL_NAME_RE.search(header)
    description_match = _DESCRIPTION_RE.search(header)
    if not name_match or name_match.group("name") != name:
        raise SkillCatalogError(f"Skill frontmatter name does not match catalog: {name}")
    skill_description = (description_match.group("quoted") or description_match.group("plain").strip()) if description_match else None
    if skill_description != entry.get("description"):
        raise SkillCatalogError(f"Skill frontmatter description does not match catalog: {name}")

    source_ids = entry.get("sources")
    if (not isinstance(source_ids, list) or not source_ids
            or any(not isinstance(source_id, str) or source_id not in sources for source_id in source_ids)):
        raise SkillCatalogError(f"Skill source references are invalid: {name}")
    if entry.get("review_status") != "reviewed":
        raise SkillCatalogError(f"Unreviewed skill cannot be served: {name}")
    if entry.get("enabled") is not False:
        raise SkillCatalogError(f"Skills must remain disabled in the static catalog: {name}")
    if entry.get("allowed_tools") != []:
        raise SkillCatalogError(f"Static skill catalog cannot grant tools: {name}")
    data_classes = entry.get("allowed_data_classes")
    if (not isinstance(data_classes, list) or not data_classes
            or any(not isinstance(value, str) for value in data_classes)
            or set(data_classes) - {"public", "synthetic"}):
        raise SkillCatalogError(f"Static skills are limited to public/synthetic data: {name}")

    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return {
        "name": name,
        "description": entry["description"],
        "category": entry["category"],
        "sources": [
            {"id": source_id, **sources[source_id]}
            for source_id in source_ids
        ],
        "recommended_departments": entry.get("recommended_departments", []),
        "review_status": entry["review_status"],
        "enabled": False,
        "allowed_data_classes": data_classes,
        "allowed_tools": [],
        "content_sha256": digest,
        "content": content,
    }


def _validated_catalog() -> list[dict[str, Any]]:
    manifest = _load_manifest()
    entries = manifest["skills"]
    if any(not isinstance(entry, dict) for entry in entries):
        raise SkillCatalogError("Skill entries must be objects")
    names = [entry.get("name") for entry in entries]
    if any(not isinstance(name, str) or not _NAME_RE.fullmatch(name) for name in names):
        raise SkillCatalogError("Skill names are invalid")
    if len(names) != len(set(names)):
        raise SkillCatalogError("Skill names must be unique")
    return [_read_entry(entry, manifest["sources"]) for entry in entries]


def list_skills(*, category: str | None = None, query: str | None = None) -> list[dict[str, Any]]:
    """Return metadata only; full instructions are loaded on explicit request."""
    skills = _validated_catalog()
    needle = (query or "").strip().casefold()
    results = []
    for skill in skills:
        if category and skill["category"] != category:
            continue
        if needle and needle not in " ".join((skill["name"], skill["description"], skill["category"])).casefold():
            continue
        results.append({key: value for key, value in skill.items() if key != "content"})
    return results


def get_skill(name: str) -> dict[str, Any]:
    """Return a single reviewed skill and its content for an authenticated caller."""
    for skill in _validated_catalog():
        if skill["name"] == name:
            return skill
    raise SkillNotFound(name)
, re.MULTILINE)
_SKILL_NAME_RE = re.compile(r"^name:\s*(?P<name>[a-z0-9-]+)\s*$", re.MULTILINE)


class SkillCatalogError(ValueError):
    """The checked-in skill catalog or a skill asset is invalid."""


class SkillNotFound(KeyError):
    """No reviewed skill exists with the requested name."""


def _load_manifest() -> dict[str, Any]:
    try:
        manifest = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SkillCatalogError("Skill catalog is unavailable or invalid") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise SkillCatalogError("Unsupported skill catalog schema version")
    if not isinstance(manifest.get("sources"), dict) or not isinstance(manifest.get("skills"), list):
        raise SkillCatalogError("Skill catalog must define sources and skills")
    for source_id, source in manifest["sources"].items():
        if not isinstance(source_id, str) or not isinstance(source, dict):
            raise SkillCatalogError("Skill source entries must be named objects")
        if not all(isinstance(source.get(field), str) and source[field].strip()
                   for field in ("repository", "revision", "license", "use")):
            raise SkillCatalogError(f"Skill source metadata is incomplete: {source_id}")
    return manifest


def _read_entry(entry: dict[str, Any], sources: dict[str, Any]) -> dict[str, Any]:
    name = entry.get("name")
    relative_path = entry.get("path")
    if not isinstance(entry, dict):
        raise SkillCatalogError("Skill entries must be objects")
    if not isinstance(name, str) or not _NAME_RE.fullmatch(name):
        raise SkillCatalogError("Skill name is invalid")
    if not isinstance(entry.get("description"), str) or not entry["description"].strip():
        raise SkillCatalogError(f"Skill description is invalid: {name}")
    if not isinstance(entry.get("category"), str) or not entry["category"].strip():
        raise SkillCatalogError(f"Skill category is invalid: {name}")
    if relative_path != f"{name}/SKILL.md":
        raise SkillCatalogError(f"Skill path must be the standard directory path: {name}")
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise SkillCatalogError(f"Unsafe skill path: {name}")
    root = SKILLS_ROOT.resolve()
    target = (root / path).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise SkillCatalogError(f"Skill path escapes the catalog root: {name}") from exc

    try:
        content = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise SkillCatalogError(f"Skill asset is missing: {name}") from exc
    match = _FRONTMATTER_RE.match(content)
    if not match:
        raise SkillCatalogError(f"Skill frontmatter is missing: {name}")
    header = match.group("header")
    name_match = _SKILL_NAME_RE.search(header)
    description_match = _DESCRIPTION_RE.search(header)
    if not name_match or name_match.group("name") != name:
        raise SkillCatalogError(f"Skill frontmatter name does not match catalog: {name}")
    skill_description = (description_match.group("quoted") or description_match.group("plain").strip()) if description_match else None
    if skill_description != entry.get("description"):
        raise SkillCatalogError(f"Skill frontmatter description does not match catalog: {name}")

    source_ids = entry.get("sources")
    if (not isinstance(source_ids, list) or not source_ids
            or any(not isinstance(source_id, str) or source_id not in sources for source_id in source_ids)):
        raise SkillCatalogError(f"Skill source references are invalid: {name}")
    if entry.get("review_status") != "reviewed":
        raise SkillCatalogError(f"Unreviewed skill cannot be served: {name}")
    if entry.get("enabled") is not False:
        raise SkillCatalogError(f"Skills must remain disabled in the static catalog: {name}")
    if entry.get("allowed_tools") != []:
        raise SkillCatalogError(f"Static skill catalog cannot grant tools: {name}")
    data_classes = entry.get("allowed_data_classes")
    if (not isinstance(data_classes, list) or not data_classes
            or any(not isinstance(value, str) for value in data_classes)
            or set(data_classes) - {"public", "synthetic"}):
        raise SkillCatalogError(f"Static skills are limited to public/synthetic data: {name}")

    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return {
        "name": name,
        "description": entry["description"],
        "category": entry["category"],
        "sources": [
            {"id": source_id, **sources[source_id]}
            for source_id in source_ids
        ],
        "recommended_departments": entry.get("recommended_departments", []),
        "review_status": entry["review_status"],
        "enabled": False,
        "allowed_data_classes": data_classes,
        "allowed_tools": [],
        "content_sha256": digest,
        "content": content,
    }


def _validated_catalog() -> list[dict[str, Any]]:
    manifest = _load_manifest()
    entries = manifest["skills"]
    if any(not isinstance(entry, dict) for entry in entries):
        raise SkillCatalogError("Skill entries must be objects")
    names = [entry.get("name") for entry in entries]
    if any(not isinstance(name, str) or not _NAME_RE.fullmatch(name) for name in names):
        raise SkillCatalogError("Skill names are invalid")
    if len(names) != len(set(names)):
        raise SkillCatalogError("Skill names must be unique")
    return [_read_entry(entry, manifest["sources"]) for entry in entries]


def list_skills(*, category: str | None = None, query: str | None = None) -> list[dict[str, Any]]:
    """Return metadata only; full instructions are loaded on explicit request."""
    skills = _validated_catalog()
    needle = (query or "").strip().casefold()
    results = []
    for skill in skills:
        if category and skill["category"] != category:
            continue
        if needle and needle not in " ".join((skill["name"], skill["description"], skill["category"])).casefold():
            continue
        results.append({key: value for key, value in skill.items() if key != "content"})
    return results


def get_skill(name: str) -> dict[str, Any]:
    """Return a single reviewed skill and its content for an authenticated caller."""
    for skill in _validated_catalog():
        if skill["name"] == name:
            return skill
    raise SkillNotFound(name)
