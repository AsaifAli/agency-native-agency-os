"""Deterministic data-protection boundary for agent execution payloads.

This is a conservative first boundary, not a complete classifier or compliance
certification. Every provider-facing structured payload must pass this gateway.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, replace
from typing import Any

from app.integrations.runtime import ExecutionRequest, ExecutionResult
from app.models import DataClass

MAX_METADATA_BYTES = 32_768
MAX_EXECUTION_REQUEST_BYTES = 65_536
MAX_RUNTIME_DETAIL_CHARS = 16_000
MAX_METADATA_DEPTH = 6
MAX_CONTAINER_ITEMS = 100


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


def _bounded_json_size(value: Any) -> int:
    try:
        return len(json.dumps(
            value, ensure_ascii=False, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8"))
    except (TypeError, ValueError, OverflowError) as exc:
        raise DataProtectionBlocked("UNSUPPORTED_METADATA") from exc


def _sanitize_value(value: Any, counts: dict[str, int], depth: int = 0) -> Any:
    if depth > MAX_METADATA_DEPTH:
        raise DataProtectionBlocked("METADATA_TOO_DEEP")
    if isinstance(value, str):
        cleaned, found = sanitize_text(value)
        for key, count in found.items():
            counts[key] = counts.get(key, 0) + count
        return cleaned
    if isinstance(value, list):
        if len(value) > MAX_CONTAINER_ITEMS:
            raise DataProtectionBlocked("METADATA_TOO_LARGE")
        return [_sanitize_value(item, counts, depth + 1) for item in value]
    if isinstance(value, dict):
        if len(value) > MAX_CONTAINER_ITEMS:
            raise DataProtectionBlocked("METADATA_TOO_LARGE")
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise DataProtectionBlocked("INVALID_METADATA_KEY")
            safe_key, found = sanitize_text(key)
            for label, count in found.items():
                counts[label] = counts.get(label, 0) + count
            if safe_key in cleaned:
                raise DataProtectionBlocked("DUPLICATE_SANITIZED_METADATA_KEY")
            cleaned[safe_key] = _sanitize_value(item, counts, depth + 1)
        return cleaned
    if value is None or isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise DataProtectionBlocked("NON_FINITE_NUMBER")
        return value
    raise DataProtectionBlocked("UNSUPPORTED_METADATA")


def _validate_runtime_identifier(value: str | None) -> str | None:
    """Reject PII/secrets in identifiers because redaction would break correlation."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise DataProtectionBlocked("INVALID_RUNTIME_IDENTIFIER")
    cleaned, counts = sanitize_text(value)
    if counts or cleaned != value:
        raise DataProtectionBlocked("SENSITIVE_RUNTIME_IDENTIFIER")
    return value


def protect_execution_result(
    result: ExecutionResult,
) -> tuple[ExecutionResult, DataProtectionReport]:
    """Protect every provider-returned string before persistence."""
    if (
        not isinstance(result, ExecutionResult)
        or not isinstance(result.provider, str)
        or not isinstance(result.detail, str)
        or len(result.detail) > MAX_RUNTIME_DETAIL_CHARS
    ):
        raise DataProtectionBlocked("INVALID_RUNTIME_RESULT")
    provider = _validate_runtime_identifier(result.provider)
    external_run_id = _validate_runtime_identifier(result.external_run_id)
    cleaned, counts = sanitize_text(result.detail)
    return (
        replace(result, provider=provider, external_run_id=external_run_id, detail=cleaned),
        DataProtectionReport(redaction_counts=counts),
    )


def protect_execution_request(
    request: ExecutionRequest,
) -> tuple[ExecutionRequest, DataProtectionReport]:
    """Return a sanitized copy; never mutate or persist raw provider payloads."""
    if not isinstance(request, ExecutionRequest):
        raise DataProtectionBlocked("INVALID_EXECUTION_REQUEST")
    if not isinstance(request.data_class, DataClass) or not isinstance(request.client_authorized, bool):
        raise DataProtectionBlocked("INVALID_EXECUTION_POLICY")
    if request.data_class in {DataClass.confidential, DataClass.regulated}:
        raise DataProtectionBlocked("DATA_CLASS_NOT_ELIGIBLE")
    if request.data_class == DataClass.commercial and not request.client_authorized:
        raise DataProtectionBlocked("CLIENT_AUTHORIZATION_REQUIRED")

    metadata = request.request_metadata if request.request_metadata is not None else {}
    if not isinstance(metadata, dict):
        raise DataProtectionBlocked("INVALID_METADATA")
    if _bounded_json_size(metadata) > MAX_METADATA_BYTES:
        raise DataProtectionBlocked("METADATA_TOO_LARGE")

    counts: dict[str, int] = {}
    identifier_fields = {
        "org_id": request.org_id,
        "workspace_id": request.workspace_id,
        "task_id": request.task_id,
        "agent_id": request.agent_id,
        "external_run_id": request.external_run_id,
    }
    for key in ("org_id", "workspace_id", "task_id", "agent_id"):
        if not isinstance(identifier_fields[key], str) or not identifier_fields[key]:
            raise DataProtectionBlocked("INVALID_RUNTIME_IDENTIFIER")
    safe_identifiers = {
        key: _validate_runtime_identifier(value)
        for key, value in identifier_fields.items()
    }
    values = {
        "agent_name": request.agent_name,
        "agent_department": request.agent_department,
        "agent_instructions": request.agent_instructions,
        "task_title": request.task_title,
        "task_description": request.task_description,
    }
    if any(not isinstance(value, str) for value in values.values()):
        raise DataProtectionBlocked("INVALID_TEXT")
    raw_payload = {**safe_identifiers, **values, "request_metadata": metadata}
    if _bounded_json_size(raw_payload) > MAX_EXECUTION_REQUEST_BYTES:
        raise DataProtectionBlocked("EXECUTION_REQUEST_TOO_LARGE")
    safe_metadata = _sanitize_value(metadata, counts)
    if _bounded_json_size(safe_metadata) > MAX_METADATA_BYTES:
        raise DataProtectionBlocked("METADATA_TOO_LARGE")
    cleaned = {
        key: _sanitize_value(value, counts)
        for key, value in values.items()
    }
    request_payload = {**safe_identifiers, **cleaned, "request_metadata": safe_metadata}
    if _bounded_json_size(request_payload) > MAX_EXECUTION_REQUEST_BYTES:
        raise DataProtectionBlocked("EXECUTION_REQUEST_TOO_LARGE")

    original_persist_callback = request.persist_external_run_id

    def persist_protected_external_run_id(external_run_id: str) -> None:
        if not isinstance(external_run_id, str) or not external_run_id:
            raise DataProtectionBlocked("INVALID_RUNTIME_IDENTIFIER")
        safe_external_run_id = _validate_runtime_identifier(external_run_id)
        if original_persist_callback is not None:
            original_persist_callback(safe_external_run_id)

    protected = replace(
        request,
        **safe_identifiers,
        agent_name=cleaned["agent_name"],
        agent_department=cleaned["agent_department"],
        agent_instructions=cleaned["agent_instructions"],
        task_title=cleaned["task_title"],
        task_description=cleaned["task_description"],
        request_metadata=safe_metadata,
        persist_external_run_id=(
            persist_protected_external_run_id
            if original_persist_callback is not None else None
        ),
    )
    return protected, DataProtectionReport(redaction_counts=dict(counts))
