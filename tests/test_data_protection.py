import pytest

from app.data_protection import (
    DataProtectionBlocked,
    protect_execution_request,
    sanitize_text,
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
