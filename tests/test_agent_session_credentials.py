import hashlib
import re
import pytest

from app.agent_session_credentials import (
    issue_agent_session_credential,
    parse_agent_session_credential,
)


SESSION_ID = "a1b2c3d4-e5f6-4789-9012-1234567890ab"


def test_session_credential_is_random_and_only_hash_is_persistable():
    token, token_hash, token_prefix = issue_agent_session_credential(SESSION_ID)

    assert token.startswith(f"aos_sc_{SESSION_ID}.")
    secret = token.split(".", 1)[1]
    assert len(secret) >= 40
    assert token_hash == hashlib.sha256(secret.encode("utf-8")).hexdigest()
    assert len(token_hash) == 64
    assert token_prefix == f"aos_sc_{SESSION_ID}."
    assert secret not in token_prefix


def test_session_credential_parser_binds_token_to_exact_session():
    token, expected_hash, _ = issue_agent_session_credential(SESSION_ID)

    assert parse_agent_session_credential(
        f"Bearer {token}", SESSION_ID
    ) == expected_hash

    with pytest.raises(ValueError):
        parse_agent_session_credential(f"Bearer {token}", "b1b2c3d4-e5f6-4789-9012-1234567890ab")


@pytest.mark.parametrize(
    "authorization,session_id",
    [
        (None, SESSION_ID),
        ("", SESSION_ID),
        ("Basic abc", SESSION_ID),
        ("Bearer aos_sc_not-a-session.secret", SESSION_ID),
        ("Bearer aos_sc_" + SESSION_ID + ".", SESSION_ID),
        ("Bearer aos_sc_" + SESSION_ID + "." + ("x" * 600), SESSION_ID),
        ("Bearer aos_sc_" + SESSION_ID + ".secret", "invalid-session"),
    ],
)
def test_session_credential_parser_rejects_malformed_or_unbound_tokens(authorization, session_id):
    with pytest.raises(ValueError):
        parse_agent_session_credential(authorization, session_id)


def test_session_credential_model_is_workspace_and_execution_scoped():
    from app.security_models import AgentSessionCredential

    table = AgentSessionCredential.__table__
    assert table.name == "agent_session_credentials"
    assert {"org_id", "workspace_id", "execution_id", "agent_session_id",
            "machine_identity_id", "token_hash", "expires_at", "revoked_at",
            "provider_vault_id", "provider_credential_id"} <= set(table.columns.keys())
    assert any(c.name == "uq_agent_session_credential_execution" for c in table.constraints)
    assert any(c.name == "uq_agent_session_credential_session" for c in table.constraints)
