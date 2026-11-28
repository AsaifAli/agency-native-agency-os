"""Live catalog audit for SECURITY DEFINER ownership and ACL defaults."""
import os

import pytest
from sqlalchemy import create_engine, text

ADMIN_URL = os.getenv("AGENCY_OS_TEST_RLS_ADMIN_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not ADMIN_URL,
    reason="Set AGENCY_OS_TEST_RLS_ADMIN_DATABASE_URL for PostgreSQL function catalog audit",
)


def test_security_definer_functions_are_migrator_owned_fixed_path_and_not_publicly_executable():
    engine = create_engine(ADMIN_URL, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            rows = connection.execute(text("""
                SELECT n.nspname,
                       p.proname,
                       pg_get_function_identity_arguments(p.oid) AS identity_arguments,
                       owner.rolname AS owner_name,
                       COALESCE(array_to_string(p.proconfig, ','), '') AS function_config,
                       EXISTS (
                           SELECT 1
                           FROM aclexplode(COALESCE(p.proacl, acldefault('f', p.proowner))) AS acl
                           WHERE acl.grantee = 0 AND acl.privilege_type = 'EXECUTE'
                       ) AS public_execute
                  FROM pg_catalog.pg_proc AS p
                  JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
                  JOIN pg_catalog.pg_roles AS owner ON owner.oid = p.proowner
                 WHERE p.prosecdef IS TRUE
                 ORDER BY n.nspname, p.proname, identity_arguments
            """)).all()
        assert rows, "Expected SECURITY DEFINER functions to be present"
        failures = []
        for row in rows:
            if row.nspname != "agency_os_private":
                failures.append(f"{row.nspname}.{row.proname}: outside private schema")
            if row.owner_name != "agency_os_migrator":
                failures.append(f"{row.proname}: owner={row.owner_name}")
            if "search_path=pg_catalog" not in row.function_config:
                failures.append(f"{row.proname}: missing fixed pg_catalog-first search_path")
            if row.public_execute:
                failures.append(f"{row.proname}: PUBLIC has EXECUTE")
        assert not failures, "SECURITY DEFINER catalog violations:\n" + "\n".join(failures)
    finally:
        engine.dispose()
