import hashlib
import pytest

from app.session_credentials import _parse_bearer


SESSION_ID = "a1b2c3d4-e5f6-4789-9012-1234567890ab"
CREDENTIAL_ID = "a1b2c3d4-e5f6-4789-9012-1234567890ab"


def _token(secret="x" * 43):
    return f"aos_ms_{CREDENTIAL_ID}.{secret}"


def test_session_credential_parser_returns_only_hash_material_and_credential_id():
    token = _token()
    credential_id, secret, digest = _parse_bearer(f"Bearer {token}")

    assert credential_id == CREDENTIAL_ID
    assert secret == "x" * 43
    assert digest == hashlib.sha256(secret.encode("utf-8")).hexdigest()
    assert len(digest) == 64


def test_session_credential_parser_rejects_malformed_or_unbound_tokens():
    malformed = [
        None,
        "",
        "Basic abc",
        "Bearer aos_ms_not-a-uuid." + ("x" * 43),
        "Bearer aos_ms_" + CREDENTIAL_ID + ".",
        "Bearer aos_ms_" + CREDENTIAL_ID + "." + ("x" * 600),
        "Bearer aos_sc_" + SESSION_ID + "." + ("x" * 43),
    ]
    for authorization in malformed:
        with pytest.raises(Exception):
            _parse_bearer(authorization)


def test_session_credential_model_is_workspace_and_agent_session_scoped():
    from app.security_models import MachineSessionCredential

    table = MachineSessionCredential.__table__
    assert table.name == "machine_session_credentials"
    assert {
        "org_id", "workspace_id", "machine_identity_id", "session_id",
        "token_hash", "expires_at", "revoked_at", "provider_vault_id",
        "provider_credential_id",
    } <= set(table.columns.keys())
    assert any(c.name == "uq_machine_session_credential_token_hash" for c in table.constraints)
    assert any(c.name == "uq_machine_session_credential_version" for c in table.constraints)
    assert any(c.name == "fk_machine_session_credential_session_identity_scope" for c in table.constraints)
