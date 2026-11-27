import pytest

from app.data_protection import (
    DataProtectionBlocked,
    protect_execution_request,
    sanitize_text,
    protect_untrusted_payload,
)
from app.integrations.runtime import ExecutionRequest
from app.models import DataClass


def _request(**overrides):
    values = {
        "org_id": "org-1",
        "workspace_id": "workspace-1",
        "task_id": "task-1",
        "agent_id": "agent-1",
        "data_class": DataClass.public,
        "agent_name": "Research Analyst",
        "agent_department": "Market Research",
        "agent_instructions": "Use public sources and cite evidence.",
        "task_title": "Research public AI trends",
        "task_description": "Summarize public market information.",
        "request_metadata": {"purpose": "research.execute"},
    }
    values.update(overrides)
    return ExecutionRequest(**values)


def test_sanitize_text_redacts_high_confidence_personal_identifiers():
    raw = (
        "Contact jane.doe@example.com, call +91 98765 43210, "
        "Aadhaar 1234 5678 9012, PAN ABCDE1234F, card 4111 1111 1111 1111."
    )
    cleaned, counts = sanitize_text(raw)
    assert "jane.doe@example.com" not in cleaned
    assert "98765 43210" not in cleaned
    assert "1234 5678 9012" not in cleaned
    assert "ABCDE1234F" not in cleaned
    assert "4111 1111 1111 1111" not in cleaned
    assert counts == {
        "EMAIL": 1,
        "GOVERNMENT_ID": 2,
        "PAYMENT_CARD": 1,
        "PHONE": 1,
    }


def test_sanitize_text_blocks_secrets_without_echoing_secret_value():
    secret = "sk-ant-api-1234567890abcdefghijkl"
    with pytest.raises(DataProtectionBlocked) as error:
        sanitize_text(f"Use this key: {secret}")
    assert error.value.code == "SECRET_DETECTED"
    assert secret not in str(error.value)


def test_protect_execution_request_redacts_nested_metadata_and_prompt_fields():
    request = _request(
        task_description="Contact founder at founder@example.com",
        request_metadata={"source": {"email": "research@example.com"}},
    )
    protected, report = protect_execution_request(request)
    assert "founder@example.com" not in protected.task_description
    assert protected.request_metadata["source"]["email"] == "[REDACTED_EMAIL]"
    assert report.redaction_counts["EMAIL"] == 2
    assert request.task_description == "Contact founder at founder@example.com"


@pytest.mark.parametrize("data_class", [DataClass.confidential, DataClass.regulated])
def test_protect_execution_request_blocks_restricted_data_classes(data_class):
    with pytest.raises(DataProtectionBlocked) as error:
        protect_execution_request(_request(data_class=data_class))
    assert error.value.code == "DATA_CLASS_NOT_ELIGIBLE"


def test_protect_execution_request_requires_authorization_for_commercial_data():
    with pytest.raises(DataProtectionBlocked) as error:
        protect_execution_request(_request(data_class=DataClass.commercial))
    assert error.value.code == "CLIENT_AUTHORIZATION_REQUIRED"


def test_protect_execution_request_allows_authorized_commercial_after_redaction():
    protected, report = protect_execution_request(_request(
        data_class=DataClass.commercial,
        client_authorized=True,
        task_description="Use contact billing@example.com only as a redacted reference.",
    ))
    assert "billing@example.com" not in protected.task_description
    assert report.redaction_counts == {"EMAIL": 1}

from app.data_protection import protect_execution_result
from app.integrations.runtime import ExecutionResult


def test_protect_execution_result_redacts_personal_data_before_persistence():
    result = ExecutionResult(
        provider="test", external_run_id="run-1", status="succeeded",
        detail="Contact billing@example.com or call +91 98765 43210.",
    )
    protected, report = protect_execution_result(result)
    assert "billing@example.com" not in protected.detail
    assert "98765 43210" not in protected.detail
    assert report.redaction_counts == {"EMAIL": 1, "PHONE": 1}
    assert result.detail == "Contact billing@example.com or call +91 98765 43210."


def test_protect_execution_result_blocks_secret_output():
    result = ExecutionResult(
        provider="test", external_run_id="run-2", status="succeeded",
        detail="Credential: sk-ant-api-1234567890abcdefghijkl",
    )
    with pytest.raises(DataProtectionBlocked) as error:
        protect_execution_result(result)
    assert error.value.code == "SECRET_DETECTED"


def test_protect_execution_request_sanitizes_sensitive_metadata_keys():
    request = _request(request_metadata={"owner@example.com": "public"})
    protected, report = protect_execution_request(request)
    assert "owner@example.com" not in protected.request_metadata
    assert "[REDACTED_EMAIL]" in protected.request_metadata
    assert report.redaction_counts["EMAIL"] == 1


@pytest.mark.parametrize("metadata", [
    {1: "non-string key"},
    {"nested": {"bad": float("nan")}},
    {"nested": {"bad": float("inf")}},
    {"x": "a" * 40_000},
])
def test_protect_execution_request_rejects_unsafe_or_oversized_metadata(metadata):
    with pytest.raises(DataProtectionBlocked):
        protect_execution_request(_request(request_metadata=metadata))


def test_protect_execution_request_rejects_key_collisions_after_redaction():
    metadata = {
        "founder@example.com": "first",
        "[REDACTED_EMAIL]": "second",
    }
    with pytest.raises(DataProtectionBlocked) as error:
        protect_execution_request(_request(request_metadata=metadata))
    assert error.value.code == "DUPLICATE_SANITIZED_METADATA_KEY"


def test_protect_execution_result_redacts_and_blocks_provider_output():
    result = ExecutionResult(
        provider="test", external_run_id="run-3", status="succeeded",
        detail="Send to ops@example.com",
    )
    protected, report = protect_execution_result(result)
    assert "ops@example.com" not in protected.detail
    assert report.redaction_counts == {"EMAIL": 1}

    secret_result = ExecutionResult(
        provider="test", external_run_id="run-4", status="succeeded",
        detail="token=sk-ant-api-1234567890abcdefghijkl",
    )
    with pytest.raises(DataProtectionBlocked) as error:
        protect_execution_result(secret_result)
    assert error.value.code == "SECRET_DETECTED"


def test_protect_execution_request_rejects_oversized_prompt_and_non_dict_metadata():
    with pytest.raises(DataProtectionBlocked) as oversized:
        protect_execution_request(_request(task_description="x" * 70_000))
    assert oversized.value.code == "EXECUTION_REQUEST_TOO_LARGE"

    with pytest.raises(DataProtectionBlocked) as invalid:
        protect_execution_request(_request(request_metadata=["not", "an", "object"]))
    assert invalid.value.code == "INVALID_METADATA"


def test_protect_execution_request_wraps_external_run_id_persistence_callback():
    persisted = []
    request = _request(persist_external_run_id=persisted.append)
    protected, _ = protect_execution_request(request)
    protected.persist_external_run_id("provider-run-123")
    assert persisted == ["provider-run-123"]

    with pytest.raises(DataProtectionBlocked) as error:
        protected.persist_external_run_id("owner@example.com")
    assert error.value.code == "SENSITIVE_RUNTIME_IDENTIFIER"
    assert persisted == ["provider-run-123"]


@pytest.mark.parametrize("result", [
    ExecutionResult(
        provider="provider", external_run_id="owner@example.com",
        status="succeeded", detail="safe",
    ),
    ExecutionResult(
        provider="provider@example.com", external_run_id="run-123",
        status="succeeded", detail="safe",
    ),
])
def test_protect_execution_result_blocks_sensitive_provider_identifiers(result):
    with pytest.raises(DataProtectionBlocked) as error:
        protect_execution_result(result)
    assert error.value.code == "SENSITIVE_RUNTIME_IDENTIFIER"


def test_protect_execution_request_requires_nonempty_scope_identifiers():
    with pytest.raises(DataProtectionBlocked) as error:
        protect_execution_request(_request(workspace_id=""))
    assert error.value.code == "INVALID_RUNTIME_IDENTIFIER"

    with pytest.raises(DataProtectionBlocked) as error:
        protect_execution_request(_request(agent_id=None))
    assert error.value.code == "INVALID_RUNTIME_IDENTIFIER"


def test_protect_execution_request_rejects_invalid_request_policy_types():
    with pytest.raises(DataProtectionBlocked) as invalid_request:
        protect_execution_request(None)
    assert invalid_request.value.code == "INVALID_EXECUTION_REQUEST"

    with pytest.raises(DataProtectionBlocked) as invalid_class:
        protect_execution_request(_request(data_class="public"))
    assert invalid_class.value.code == "INVALID_EXECUTION_POLICY"

    with pytest.raises(DataProtectionBlocked) as invalid_authorization:
        protect_execution_request(_request(
            data_class=DataClass.commercial,
            client_authorized="true",
        ))
    assert invalid_authorization.value.code == "INVALID_EXECUTION_POLICY"


def test_protect_untrusted_payload_redacts_nested_values_and_keys():
    payload = {
        "owner@example.com": {
            "contact": "billing@example.com",
            "notes": ["Call +91 98765 43210"],
        }
    }
    protected, report = protect_untrusted_payload(payload)
    assert "owner@example.com" not in protected
    assert "[REDACTED_EMAIL]" in protected
    assert protected["[REDACTED_EMAIL]"]["contact"] == "[REDACTED_EMAIL]"
    assert report.redaction_counts == {"EMAIL": 2, "PHONE": 1}


def test_protect_untrusted_payload_rejects_oversized_or_non_json_values():
    with pytest.raises(DataProtectionBlocked) as oversized:
        protect_untrusted_payload({"large": "x" * 70_000})
    assert oversized.value.code == "UNTRUSTED_PAYLOAD_TOO_LARGE"

    with pytest.raises(DataProtectionBlocked):
        protect_untrusted_payload({"unsupported": object()})


def test_internal_scope_ids_are_not_misclassified_as_phone_numbers():
    protected, _ = protect_execution_request(
        _request(workspace_id="worker-ws-1234567890")
    )
    assert protected.workspace_id == "worker-ws-1234567890"


def test_provider_run_identifier_that_looks_like_phone_is_blocked():
    result = ExecutionResult(
        provider="test", external_run_id="9876543210",
        status="succeeded", detail="safe",
    )
    with pytest.raises(DataProtectionBlocked) as error:
        protect_execution_result(result)
    assert error.value.code == "SENSITIVE_RUNTIME_IDENTIFIER"


def test_tool_result_internal_resource_ids_are_exempt_only_for_explicit_keys():
    protected, _ = protect_untrusted_payload(
        {"draft_id": "draft-1234567890", "notes": "Contact owner@example.test"},
        trusted_internal_id_keys={"draft_id"},
    )
    assert protected["draft_id"] == "draft-1234567890"
    assert protected["notes"] == "Contact [REDACTED_EMAIL]"
    with pytest.raises(DataProtectionBlocked) as error:
        protect_untrusted_payload(
            {"draft_id": "not a safe id: owner@example.test"},
            trusted_internal_id_keys={"draft_id"},
        )
    assert error.value.code == "INVALID_RUNTIME_IDENTIFIER"


def test_tool_result_cannot_exempt_arbitrary_fields_from_pii_redaction():
    with pytest.raises(DataProtectionBlocked) as error:
        protect_untrusted_payload(
            {"notes": "owner@example.test"},
            trusted_internal_id_keys={"notes"},
        )
    assert error.value.code == "INVALID_TRUSTED_IDENTIFIER_POLICY"


@pytest.mark.parametrize("secret", [
    "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
    "github_pat_11AA22BB33CC44DD55_abcdefghijklmnopqrstuvwxyz0123456789",
    "xoxb-" + "1234567890-abcdefghijklmnop",
    "AIzaSyA1234567890abcdefghijklmnopqrstuv",
    "sk_live_" + "1234567890abcdefghijklmnop",
    "rk_test_1234567890abcdefghijklmnop",
    "whsec_1234567890abcdefghijklmnop",
    "SG.1234567890abcdefghijklmnop.1234567890abcdefghijklmnop",
    "sk-or-v1-1234567890abcdefghijklmnopqrstuv",
    "re_1234567890abcdefghijklmnopqrstuv",
    "sb_secret_1234567890abcdefghijklmnopqrstuv",
    "hf_1234567890abcdefghijklmnopqrstuv",
])
def test_sanitize_text_blocks_common_provider_credentials(secret):
    with pytest.raises(DataProtectionBlocked) as error:
        sanitize_text(f"Do not forward this credential: {secret}")
    assert error.value.code == "SECRET_DETECTED"
    assert secret not in str(error.value)


def test_sanitize_text_does_not_block_provider_names_or_security_discussion():
    cleaned, counts = sanitize_text(
        "Discuss GitHub PAT rotation, OpenRouter, Resend, Supabase, and Hugging Face integrations."
    )
    assert cleaned == (
        "Discuss GitHub PAT rotation, OpenRouter, Resend, Supabase, and Hugging Face integrations."
    )
    assert counts == {}


def test_sanitize_text_blocks_generic_secret_and_token_assignments():
    for value in ("secret=abcdefgh12345678", "refresh_token: abcdefgh12345678"):
        with pytest.raises(DataProtectionBlocked) as error:
            sanitize_text(value)
        assert error.value.code == "SECRET_DETECTED"


def test_trusted_internal_id_keys_are_preserved_inside_nested_arrays():
    protected, report = protect_untrusted_payload(
        {"results": [{"draft_id": "draft-1234567890"}]},
        trusted_internal_id_keys={"draft_id"},
    )
    assert protected["results"][0]["draft_id"] == "draft-1234567890"
    assert report.total_redactions == 0


def test_protect_execution_request_wraps_provider_event_persistence_callbacks():
    persisted = []
    request = _request(
        persist_resume_event=lambda token, event_id: persisted.append(("resume", token, event_id)),
        persist_control_event=lambda action, event_id: persisted.append((action, event_id)),
    )
    protected, _ = protect_execution_request(request)

    protected.persist_resume_event("resume-token-123", "provider-event-123")
    protected.persist_control_event("pause", "provider-event-456")

    assert persisted == [
        ("resume", "resume-token-123", "provider-event-123"),
        ("pause", "provider-event-456"),
    ]


@pytest.mark.parametrize(
    "provider_event_id",
    ["owner@example.test", "sk-or-v1-1234567890abcdefghijklmnopqrstuv", "e" * 201],
)
def test_protect_execution_request_blocks_unsafe_provider_event_ids(provider_event_id):
    persisted = []
    request = _request(
        persist_control_event=lambda action, event_id: persisted.append((action, event_id)),
    )
    protected, _ = protect_execution_request(request)

    with pytest.raises(DataProtectionBlocked):
        protected.persist_control_event("pause", provider_event_id)
    assert persisted == []


def test_protect_execution_request_validates_persisted_provider_event_ids_in_metadata():
    request = _request(request_metadata={
        "control_request": {
            "action": "resume",
            "resume_token": "resume-token-123",
            "resume_event_id": "owner@example.test",
        },
    })
    with pytest.raises(DataProtectionBlocked) as error:
        protect_execution_request(request)
    assert error.value.code == "SENSITIVE_RUNTIME_IDENTIFIER"


def test_protect_execution_request_rejects_invalid_control_metadata():
    request = _request(request_metadata={
        "control_request": {"action": "run_anything", "resume_token": "resume-token-123"},
    })
    with pytest.raises(DataProtectionBlocked) as error:
        protect_execution_request(request)
    assert error.value.code == "INVALID_CONTROL_METADATA"


def test_protect_execution_request_blocks_unsupported_control_callback_actions():
    persisted = []
    request = _request(
        persist_control_event=lambda action, event_id: persisted.append((action, event_id)),
    )
    protected, _ = protect_execution_request(request)

    with pytest.raises(DataProtectionBlocked) as error:
        protected.persist_control_event("resume", "provider-event-123")
    assert error.value.code == "INVALID_CONTROL_ACTION"
    assert persisted == []


@pytest.mark.parametrize(
    "credential_key",
    ["token", "api_key", "ApiKey", "provider.accessToken", "provider_access_token", "client_secret", "private_key", "password", "authorization"],
)
def test_protect_untrusted_payload_blocks_structured_credential_fields(credential_key):
    with pytest.raises(DataProtectionBlocked) as error:
        protect_untrusted_payload({credential_key: "opaque-credential-fixture"})
    assert error.value.code == "SECRET_FIELD_DETECTED"


def test_protect_untrusted_payload_allows_explicit_nonsecret_token_metadata():
    protected, _ = protect_untrusted_payload({
        "token_prefix": "aos_mi_test.",
        "token_count": 12,
        "input_tokens": 100,
        "output_tokens": 50,
    })
    assert protected == {
        "token_prefix": "aos_mi_test.",
        "token_count": 12,
        "input_tokens": 100,
        "output_tokens": 50,
    }


def test_resume_tokens_are_only_allowed_as_validated_internal_identifiers():
    with pytest.raises(DataProtectionBlocked) as error:
        protect_untrusted_payload({"resume_token": "resume-token-123"})
    assert error.value.code == "SECRET_FIELD_DETECTED"

    protected, _ = protect_untrusted_payload(
        {"resume_token": "resume-token-123"},
        trusted_internal_id_keys={"resume_token"},
    )
    assert protected["resume_token"] == "resume-token-123"


def test_execution_metadata_blocks_structured_credentials_but_allows_resume_control_token():
    unsafe = _request(request_metadata={"provider": {"api_key": "opaque-credential-fixture"}})
    with pytest.raises(DataProtectionBlocked) as error:
        protect_execution_request(unsafe)
    assert error.value.code == "SECRET_FIELD_DETECTED"

    safe = _request(request_metadata={
        "control_request": {"action": "resume", "resume_token": "resume-token-123"},
    })
    protected, _ = protect_execution_request(safe)
    assert protected.request_metadata["control_request"]["resume_token"] == "resume-token-123"


def test_trusted_internal_metadata_keys_are_case_sensitive():
    with pytest.raises(DataProtectionBlocked) as error:
        protect_untrusted_payload(
            {"ResumeToken": "resume-token-123"},
            trusted_internal_id_keys={"resume_token"},
        )
    assert error.value.code == "SECRET_FIELD_DETECTED"


def test_nonsecret_token_metadata_is_type_checked():
    with pytest.raises(DataProtectionBlocked) as error:
        protect_untrusted_payload({"token_prefix": "full-token-fixture"})
    assert error.value.code == "INVALID_TOKEN_PREFIX"

    for invalid_count in ("opaque-token-fixture", -1, 1_000_000_001):
        with pytest.raises(DataProtectionBlocked) as error:
            protect_untrusted_payload({"token_count": invalid_count})
        assert error.value.code == "INVALID_TOKEN_USAGE"


def test_protect_untrusted_payload_redacts_structured_personal_fields_recursively():
    protected, report = protect_untrusted_payload({
        "contacts": [{
            "first_name": "test-person-fixture",
            "email": "test-email-fixture",
            "phone_number": "test-phone-fixture",
            "address": "test-address-fixture",
        }],
        "company_name": "Example Company",
    })

    contact = protected["contacts"][0]
    assert contact["first_name"] == "[REDACTED_PII_FIELD]"
    assert contact["email"] == "[REDACTED_PII_FIELD]"
    assert contact["phone_number"] == "[REDACTED_PII_FIELD]"
    assert contact["address"] == "[REDACTED_PII_FIELD]"
    assert protected["company_name"] == "Example Company"
    assert report.redaction_counts["STRUCTURED_PII"] == 4
