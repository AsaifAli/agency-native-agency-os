import pytest

from app.audit import record_event
from app.data_protection import DataProtectionBlocked


class RecordingSession:
    def __init__(self):
        self.added = []

    def add(self, value):
        self.added.append(value)


def test_record_event_redacts_personal_data_before_persistence():
    db = RecordingSession()

    event = record_event(
        db,
        "org-1",
        "user-1",
        "lead.note_added",
        "lead",
        "lead-1",
        "workspace-1",
        {
            "note": "Contact founder@example.com or +91 98765 43210",
            "contact_name": "test-person-fixture",
        },
    )

    assert event is db.added[0]
    assert event.payload["contact_name"] == "[REDACTED_PII_FIELD]"
    assert "founder@example.com" not in event.payload["note"]
    assert "+91 98765 43210" not in event.payload["note"]
    assert "[REDACTED_EMAIL]" in event.payload["note"]
    assert "[REDACTED_PHONE]" in event.payload["note"]


def test_record_event_rejects_secret_bearing_payloads():
    db = RecordingSession()

    with pytest.raises(DataProtectionBlocked) as error:
        record_event(
            db,
            "org-1",
            "user-1",
            "integration.updated",
            "integration",
            "integration-1",
            "workspace-1",
            {"diagnostic": "api_key=super-secret-value-123"},
        )

    assert error.value.code == "SECRET_DETECTED"
    assert db.added == []


def test_record_event_rejects_oversized_or_non_object_payloads():
    db = RecordingSession()

    with pytest.raises(DataProtectionBlocked):
        record_event(
            db,
            "org-1",
            "user-1",
            "integration.updated",
            "integration",
            "integration-1",
            "workspace-1",
            {"diagnostic": "x" * 70_000},
        )

    with pytest.raises(DataProtectionBlocked):
        record_event(
            db,
            "org-1",
            "user-1",
            "integration.updated",
            "integration",
            "integration-1",
            "workspace-1",
            ["unexpected", "list"],
        )

    assert db.added == []


def test_record_event_preserves_only_validated_resume_token_and_safe_token_prefix():
    db = RecordingSession()

    event = record_event(
        db,
        "org-1",
        "user-1",
        "execution.resume_requested",
        "execution",
        "execution-1",
        "workspace-1",
        {"resume_token": "resume-token-123", "token_prefix": "aos_mi_test."},
    )

    assert event.payload["resume_token"] == "resume-token-123"
    assert event.payload["token_prefix"] == "aos_mi_test."
