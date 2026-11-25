"""Deterministic data-protection boundary for agent execution payloads.

This gateway is intentionally conservative and is not a compliance certification.
It blocks unsupported data classes and credential-like material, and redacts
high-confidence personal identifiers before a provider runtime receives input.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any

from app.integrations.runtime import ExecutionRequest
from app.models import DataClass


class DataProtectionBlocked(Exception):
    """A request cannot be sent to an AI runtime under current policy."""

    def __init__(self, code: str):
        self.code = code
        super().__init__("Execution blocked by data-protection policy.")


@dataclass(frozen=True)
class DataProtectionReport:
    redaction_counts: dict[str, int]

    @property
    def total_redactions(self) -> int:
        return sum(self.redaction_counts.values())


_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.IGNORECASE),
    re.compile(r"\bsk-(?:ant|proj|live)-[A-Za-z0-9_-]{12,}\b", re.IGNORECASE),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}", re.IGNORECASE),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    re.compile(
        r"\b(?:api[_ -]?key|access[_ -]?token|client[_ -]?secret|password)\s*[:=]\s*"
        r"[\"']?[^\s\"',;]{8,}",
        re.IGNORECASE,
    ),
)
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_AADHAAR = re.compile(r"(?<!\d)(?:\d{4}[ -]?){2}\d{4}(?!\d)")
_PAN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b", re.IGNORECASE)
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
_PHONE = re.compile(r"(?<!\w)\+?\d[\d().\s-]{8,17}\d(?!\w)")


def _luhn_valid(value: str) -> bool:
    digits = [int(ch) for ch in value if ch.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def sanitize_text(value: str) -> tuple[str, dict[str, int]]:
    if not isinstance(value, str):
        raise DataProtectionBlocked("INVALID_TEXT")
    if any(pattern.search(value) for pattern in _SECRET_PATTERNS):
        raise DataProtectionBlocked("SECRET_DETECTED")

    text = value
    counts: dict[str, int] = {}

    def redact(pattern: re.Pattern[str], label: str) -> None:
        nonlocal text
        text, count = pattern.subn(f"[REDACTED_{label}]", text)
        if count:
            counts[label] = counts.get(label, 0) + count

    redact(_EMAIL, "EMAIL")
    redact(_PAN, "GOVERNMENT_ID")

    # Detect valid payment-card numbers before the broader 12-digit
    # government-ID pattern, otherwise a card prefix can be misclassified.
    def redact_card(match: re.Match[str]) -> str:
        raw = match.group(0)
        if _luhn_valid(raw):
            counts["PAYMENT_CARD"] = counts.get("PAYMENT_CARD", 0) + 1
            return "[REDACTED_PAYMENT_CARD]"
        return raw

    text = _CARD.sub(redact_card, text)
    redact(_AADHAAR, "GOVERNMENT_ID")

    def redact_phone(match: re.Match[str]) -> str:
        raw = match.group(0)
        digits = sum(character.isdigit() for character in raw)
        if 10 <= digits <= 15:
            counts["PHONE"] = counts.get("PHONE", 0) + 1
            return "[REDACTED_PHONE]"
        return raw

    text = _PHONE.sub(redact_phone, text)
    return text, counts


def _sanitize_value(value: Any, counts: dict[str, int], depth: int = 0) -> Any:
    if depth > 6:
        raise DataProtectionBlocked("METADATA_TOO_DEEP")
    if isinstance(value, str):
        cleaned, found = sanitize_text(value)
        for key, count in found.items():
            counts[key] = counts.get(key, 0) + count
        return cleaned
    if isinstance(value, list):
        if len(value) > 100:
            raise DataProtectionBlocked("METADATA_TOO_LARGE")
        return [_sanitize_value(item, counts, depth + 1) for item in value]
    if isinstance(value, dict):
        if len(value) > 100:
            raise DataProtectionBlocked("METADATA_TOO_LARGE")
        return {
            str(key): _sanitize_value(item, counts, depth + 1)
            for key, item in value.items()
        }
    if value is None or isinstance(value, (bool, int, float)):
        return value
    raise DataProtectionBlocked("UNSUPPORTED_METADATA")


def protect_execution_request(
    request: ExecutionRequest,
) -> tuple[ExecutionRequest, DataProtectionReport]:
    """Return a sanitized copy; never mutate or persist raw provider payloads."""
    if request.data_class in {DataClass.confidential, DataClass.regulated}:
        raise DataProtectionBlocked("DATA_CLASS_NOT_ELIGIBLE")
    if request.data_class == DataClass.commercial and not request.client_authorized:
        raise DataProtectionBlocked("CLIENT_AUTHORIZATION_REQUIRED")

    counts: dict[str, int] = {}
    values = {
        "agent_name": request.agent_name,
        "agent_department": request.agent_department,
        "agent_instructions": request.agent_instructions,
        "task_title": request.task_title,
        "task_description": request.task_description,
    }
    cleaned = {}
    for key, value in values.items():
        cleaned[key] = _sanitize_value(value or "", counts)

    metadata = _sanitize_value(request.request_metadata or {}, counts)
    protected = replace(
        request,
        agent_name=cleaned["agent_name"],
        agent_department=cleaned["agent_department"],
        agent_instructions=cleaned["agent_instructions"],
        task_title=cleaned["task_title"],
        task_description=cleaned["task_description"],
        request_metadata=metadata,
    )
    return protected, DataProtectionReport(redaction_counts=dict(counts))
