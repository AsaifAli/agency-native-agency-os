import logging

from app.log_sanitization import configure_log_redaction


def test_log_messages_redact_personal_information(caplog):
    configure_log_redaction()
    logger = logging.getLogger("agency_os.test.redaction")

    with caplog.at_level(logging.INFO, logger="agency_os.test.redaction"):
        logger.info("Contact %s at %s", "+91 98765 43210", "founder@example.com")

    assert "founder@example.com" not in caplog.text
    assert "+91 98765 43210" not in caplog.text
    assert "[REDACTED_EMAIL]" in caplog.text
    assert "[REDACTED_PHONE]" in caplog.text


def test_log_messages_replace_secret_bearing_content(caplog):
    configure_log_redaction()
    logger = logging.getLogger("agency_os.test.secret")
    secret = "sk-ant-api-1234567890abcdefghijkl"

    with caplog.at_level(logging.ERROR, logger="agency_os.test.secret"):
        logger.error("Provider failed with credential %s", secret)

    assert secret not in caplog.text
    assert "[REDACTED_SENSITIVE_LOG_VALUE]" in caplog.text


def test_exception_text_and_structured_extras_are_sanitized(caplog):
    configure_log_redaction()
    logger = logging.getLogger("agency_os.test.exception")
    bearer = "Bearer eyJabcdefghijk.abcdefghijk.abcdefghijk"

    with caplog.at_level(logging.ERROR, logger="agency_os.test.exception"):
        try:
            raise RuntimeError(f"upstream rejected {bearer}")
        except RuntimeError:
            logger.exception(
                "Provider request failed",
                extra={
                    "access_token": "do-not-log-this",
                    "email": "founder@example.com",
                    "metadata": {"contact": "client@example.com"},
                },
            )

    record = caplog.records[-1]
    assert bearer not in caplog.text
    assert "do-not-log-this" not in repr(record.__dict__)
    assert record.access_token == "[REDACTED]"
    assert record.email == "[REDACTED]"
    assert record.metadata["contact"] == "[REDACTED_EMAIL]"


def test_generic_secret_token_and_signing_key_fields_are_redacted(caplog):
    configure_log_redaction()
    logger = logging.getLogger("agency_os.test.structured_secrets")
    secret_values = {
        "token": "opaque-token-value-123",
        "secret": "opaque-secret-value-123",
        "private_key": "private-key-material-123",
        "signing_key": "signing-key-material-123",
        "jwt": "opaque-jwt-value-123",
        "customer_name": "test-person-fixture",
        "date_of_birth": "test-date-fixture",
        "account_number": "test-account-fixture",
        "metadata": {"token": "nested-token-fixture", "secret": "nested-secret-fixture"},
    }

    with caplog.at_level(logging.INFO, logger="agency_os.test.structured_secrets"):
        logger.info("Structured provider event", extra=secret_values)

    record = caplog.records[-1]
    for field, value in secret_values.items():
        if field == "metadata":
            continue
        assert value not in caplog.text
        assert getattr(record, field) == "[REDACTED]"
    assert record.metadata == {"token": "[REDACTED]", "secret": "[REDACTED]"}
    assert "nested-token-fixture" not in repr(record.metadata)
    assert "nested-secret-fixture" not in repr(record.metadata)
