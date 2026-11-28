"""Keep the shared identity directory writable only through required columns."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "versions" / "b2c3d4e5f6a7_restrict_user_identity_mutations.py"


def test_api_role_can_only_update_oidc_link_columns_on_users():
    source = MIGRATION.read_text()
    normalized = " ".join(source.split())

    assert "REVOKE ALL ON TABLE public.users FROM PUBLIC, agency_os_app, agency_os_worker" in normalized
    assert "GRANT SELECT ON TABLE public.users TO agency_os_app" in normalized
    assert "GRANT UPDATE (oidc_issuer, oidc_subject) ON TABLE public.users TO agency_os_app" in normalized


def test_user_identity_privilege_downgrade_fails_closed():
    source = MIGRATION.read_text()
    assert "Unsafe downgrade refused" in source
