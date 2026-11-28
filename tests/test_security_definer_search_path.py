"""Static regression guard for PostgreSQL SECURITY DEFINER routines.

Every migration-defined SECURITY DEFINER function must pin pg_catalog first in
its search_path. This prevents caller-controlled schemas from shadowing names
resolved by a privileged function.
"""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations" / "versions"

CREATE_FUNCTION = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+"
    r"(?P<name>(?:[A-Za-z_][A-Za-z0-9_$]*\.)?[A-Za-z_][A-Za-z0-9_$]*)\s*\(",
    re.IGNORECASE,
)
AS_DELIMITER = re.compile(r"\bAS\s+(?P<tag>\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$)", re.IGNORECASE)
SAFE_SEARCH_PATH = re.compile(
    r"\bSET\s+search_path\s*=\s*pg_catalog\s*(?:,|$)",
    re.IGNORECASE,
)


def test_every_migration_defined_security_definer_function_pins_pg_catalog_first():
    discovered = []
    unsafe = []

    for migration in sorted(MIGRATIONS.glob("*.py")):
        source = migration.read_text(encoding="utf-8")
        for match in CREATE_FUNCTION.finditer(source):
            delimiter_match = AS_DELIMITER.search(source, match.end())
            if delimiter_match is None:
                continue

            attributes = source[match.start():delimiter_match.end()]
            if not re.search(r"\bSECURITY\s+DEFINER\b", attributes, re.IGNORECASE):
                continue

            name = match.group("name")
            discovered.append(f"{migration.name}:{name}")
            if not SAFE_SEARCH_PATH.search(attributes):
                unsafe.append(f"{migration.name}:{name}")

    assert discovered, "No migration-defined SECURITY DEFINER routines were discovered"
    assert not unsafe, (
        "SECURITY DEFINER routines must set search_path with pg_catalog first: "
        + ", ".join(unsafe)
    )
