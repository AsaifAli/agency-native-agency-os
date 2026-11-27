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
MAX_RUNTIME_IDENTIFIER_CHARS = 200
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
    # Common provider token formats. These are high-confidence prefixes; keep
    # this list explicit rather than broadly blocking arbitrary opaque IDs.
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
    re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bsk-or-v1-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bre_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsb_secret_[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bhf_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bwhsec_[A-Za-z0-9+/=_-]{16,}\b"),
    re.compile(r"\bSG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bkey-[0-9a-f]{32}\b", re.IGNORECASE),
    re.compile(
        r"\b(?:api[_ -]?key|access[_ -]?token|refresh[_ -]?token|client[_ -]?secret|"
        r"secret|token|password|private[_ -]?key|signing[_ -]?key)\s*[:=]\s*"
        r"[\"']?[^\s\"',;]{8,}",
        re.IGNORECASE,
    ),
)
_SENSITIVE_METADATA_KEY = re.compile(
    r"(?:^|_)(?:authorization|api_key|api_token|access_token|refresh_token|"
    r"id_token|auth_token|session_token|provider_token|client_secret|secret|"
    r"secret_key|private_key|signing_key|encryption_key|password|passwd|"
    r"credential|credentials|cookie|bearer|jwt|token)(?:$|_)",
    re.IGNORECASE,
)
_PII_METADATA_KEY = re.compile(
    r"(?:^|_)(?:email|phone|mobile|telephone|first_name|last_name|full_name|"
    r"contact_name|customer_name|person_name|user_name|address|street_address|"
    r"postal_address|home_address|billing_address|shipping_address|postal_code|"
    r"zip_code|date_of_birth|birth_date|dob|aadhaar|pan|ssn|national_id|"
    r"passport|passport_number|driver_license|driving_license|account_number|"
    r"bank_account|iban|card_number|cvv|ip_address|geolocation|latitude|longitude)"
    r"(?:$|_)",
    re.IGNORECASE,
)
_SAFE_NONSECRET_METADATA_KEYS = frozenset({
    "token_prefix", "token_count", "input_token_count", "output_token_count",
    "input_tokens", "output_tokens", "tokens_used",
})
_TOKEN_USAGE_KEYS = _SAFE_NONSECRET_METADATA_KEYS - {"token_prefix"}
_REDACTION_COUNT_KEYS = frozenset({"email", "phone", "government_id", "payment_card", "structured_pii"})
MAX_REDACTION_COUNT = 1_000_000_000
_MACHINE_TOKEN_PREFIX = re.compile(r"^aos_mi_[A-Za-z0-9_-]{1,36}\.$")


def _normalize_metadata_key(key: str) -> str:
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    normalized = re.sub(r"([A-Z])([A-Z][a-z])", r"\1_\2", normalized)
    return normalized.lower().replace("-", "_").replace(".", "_").replace(" ", "_")


def _is_structured_pii_key(key: str) -> bool:
    return bool(_PII_METADATA_KEY.search(_normalize_metadata_key(key)))


def _is_sensitive_metadata_key(
    key: str, trusted_internal_id_keys: frozenset[str],
) -> bool:
    normalized = _normalize_metadata_key(key)
    if normalized in _SAFE_NONSECRET_METADATA_KEYS or key in trusted_internal_id_keys:
        return False
    return bool(_SENSITIVE_METADATA_KEY.search(normalized))


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


def _sanitize_value(
    value: Any, counts: dict[str, int], depth: int = 0,
    trusted_internal_id_keys: frozenset[str] = frozenset(),
    redaction_count_context: bool = False,
) -> Any:
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
        return [
            _sanitize_value(
                item, counts, depth + 1, trusted_internal_id_keys,
                redaction_count_context,
            )
            for item in value
        ]
    if isinstance(value, dict):
        if len(value) > MAX_CONTAINER_ITEMS:
            raise DataProtectionBlocked("METADATA_TOO_LARGE")
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise DataProtectionBlocked("INVALID_METADATA_KEY")
            normalized_key = _normalize_metadata_key(key)
            if _is_sensitive_metadata_key(key, trusted_internal_id_keys):
                raise DataProtectionBlocked("SECRET_FIELD_DETECTED")
            if normalized_key == "token_prefix":
                if not isinstance(item, str) or not _MACHINE_TOKEN_PREFIX.fullmatch(item):
                    raise DataProtectionBlocked("INVALID_TOKEN_PREFIX")
            if normalized_key in _TOKEN_USAGE_KEYS and (
                isinstance(item, bool)
                or not isinstance(item, int)
                or not 0 <= item <= MAX_REDACTION_COUNT
            ):
                raise DataProtectionBlocked("INVALID_TOKEN_USAGE")
            if redaction_count_context and normalized_key in _REDACTION_COUNT_KEYS and (
                isinstance(item, bool)
                or not isinstance(item, int)
                or not 0 <= item <= MAX_REDACTION_COUNT
            ):
                raise DataProtectionBlocked("INVALID_REDACTION_COUNT")
            safe_key, found = sanitize_text(key)
            for label, count in found.items():
                counts[label] = counts.get(label, 0) + count
            if safe_key in cleaned:
                raise DataProtectionBlocked("DUPLICATE_SANITIZED_METADATA_KEY")
            if redaction_count_context and normalized_key in _REDACTION_COUNT_KEYS:
                cleaned[safe_key] = item
                continue
            if _is_structured_pii_key(key):
                counts["STRUCTURED_PII"] = counts.get("STRUCTURED_PII", 0) + 1
                cleaned[safe_key] = "[REDACTED_PII_FIELD]"
                continue
            if safe_key in trusted_internal_id_keys:
                if not isinstance(item, str):
                    raise DataProtectionBlocked("INVALID_RUNTIME_IDENTIFIER")
                cleaned[safe_key] = _validate_runtime_identifier(item, internal_scope_id=True)
            else:
                cleaned[safe_key] = _sanitize_value(
                    item, counts, depth + 1, trusted_internal_id_keys,
                    redaction_count_context=(
                        normalized_key == "redaction_counts"
                        or normalized_key.endswith("_redaction_counts")
                    ),
                )
        return cleaned
    if value is None or isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise DataProtectionBlocked("NON_FINITE_NUMBER")
        return value
    raise DataProtectionBlocked("UNSUPPORTED_METADATA")


_INTERNAL_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _validate_runtime_identifier(
    value: str | None, *, internal_scope_id: bool = False,
) -> str | None:
    """Validate opaque database IDs separately from provider-returned identifiers."""
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > MAX_RUNTIME_IDENTIFIER_CHARS:
        raise DataProtectionBlocked("INVALID_RUNTIME_IDENTIFIER")
    if any(pattern.search(value) for pattern in _SECRET_PATTERNS):
        raise DataProtectionBlocked("SECRET_DETECTED")
    if internal_scope_id:
        if not _INTERNAL_ID.fullmatch(value):
            raise DataProtectionBlocked("INVALID_RUNTIME_IDENTIFIER")
        return value
    cleaned, counts = sanitize_text(value)
    if counts or cleaned != value:
        raise DataProtectionBlocked("SENSITIVE_RUNTIME_IDENTIFIER")
    return value


def protect_untrusted_payload(
    payload: Any, *, trusted_internal_id_keys: set[str] | frozenset[str] = frozenset(),
) -> tuple[Any, DataProtectionReport]:
    """Sanitize a bounded JSON-compatible tool, connector, or extracted-text payload.

    Binary file handling and caller authorization remain the responsibility of
    the upload/connector boundary; this function protects the decoded payload.
    """
    if not isinstance(payload, (dict, list)):
        raise DataProtectionBlocked("INVALID_UNTRUSTED_PAYLOAD")
    if _bounded_json_size(payload) > MAX_EXECUTION_REQUEST_BYTES:
        raise DataProtectionBlocked("UNTRUSTED_PAYLOAD_TOO_LARGE")
    counts: dict[str, int] = {}
    allowed_internal_id_keys = {
        "draft_id", "lead_id", "research_record_id", "resume_token",
    }
    if not set(trusted_internal_id_keys).issubset(allowed_internal_id_keys):
        raise DataProtectionBlocked("INVALID_TRUSTED_IDENTIFIER_POLICY")
    protected = _sanitize_value(payload, counts, trusted_internal_id_keys=frozenset(trusted_internal_id_keys))
    if _bounded_json_size(protected) > MAX_EXECUTION_REQUEST_BYTES:
        raise DataProtectionBlocked("UNTRUSTED_PAYLOAD_TOO_LARGE")
    return protected, DataProtectionReport(redaction_counts=dict(counts))


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

    control_request = metadata.get("control_request")
    if control_request is not None:
        if not isinstance(control_request, dict):
            raise DataProtectionBlocked("INVALID_CONTROL_METADATA")
        allowed_control_keys = {
            "action", "resume_token", "resume_event_id",
            "interrupt_event_id", "interrupt_action",
        }
        if set(control_request) - allowed_control_keys:
            raise DataProtectionBlocked("INVALID_CONTROL_METADATA")
        action = control_request.get("action")
        if not isinstance(action, str) or action not in {"resume", "pause", "cancel"}:
            raise DataProtectionBlocked("INVALID_CONTROL_METADATA")
        if control_request.get("resume_token") is not None:
            if action != "resume":
                raise DataProtectionBlocked("INVALID_CONTROL_METADATA")
            _validate_runtime_identifier(control_request["resume_token"])
        for identifier_key in ("resume_event_id", "interrupt_event_id"):
            identifier = control_request.get(identifier_key)
            if identifier is not None:
                _validate_runtime_identifier(identifier)
        interrupt_action = control_request.get("interrupt_action")
        if interrupt_action is not None and (
            not isinstance(interrupt_action, str)
            or interrupt_action not in {"pause", "cancel"}
        ):
            raise DataProtectionBlocked("INVALID_CONTROL_METADATA")

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
        key: _validate_runtime_identifier(
            value, internal_scope_id=key in {"org_id", "workspace_id", "task_id", "agent_id"}
        )
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
    # Resume tokens are continuation/idempotency material, not generally safe
    # metadata. Sanitize all ordinary metadata with no token exemption, then
    # validate and sanitize only the flat, explicitly allowlisted control object.
    ordinary_metadata = {
        key: value for key, value in metadata.items() if key != "control_request"
    }
    safe_metadata = _sanitize_value(ordinary_metadata, counts)
    if control_request is not None:
        safe_control_request = _sanitize_value(
            control_request, counts,
            trusted_internal_id_keys=frozenset({"resume_token"}),
        )
        safe_metadata["control_request"] = safe_control_request
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
    original_persist_resume_event = request.persist_resume_event
    original_persist_control_event = request.persist_control_event

    def persist_protected_external_run_id(external_run_id: str) -> None:
        safe_external_run_id = _validate_runtime_identifier(external_run_id)
        if original_persist_callback is not None:
            original_persist_callback(safe_external_run_id)

    def persist_protected_resume_event(resume_token: str, provider_event_id: str) -> None:
        safe_resume_token = _validate_runtime_identifier(resume_token)
        safe_provider_event_id = _validate_runtime_identifier(provider_event_id)
        if original_persist_resume_event is not None:
            original_persist_resume_event(safe_resume_token, safe_provider_event_id)

    def persist_protected_control_event(action: str, provider_event_id: str) -> None:
        if not isinstance(action, str) or action not in {"pause", "cancel"}:
            raise DataProtectionBlocked("INVALID_CONTROL_ACTION")
        safe_provider_event_id = _validate_runtime_identifier(provider_event_id)
        if original_persist_control_event is not None:
            original_persist_control_event(action, safe_provider_event_id)

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
        persist_resume_event=(
            persist_protected_resume_event
            if original_persist_resume_event is not None else None
        ),
        persist_control_event=(
            persist_protected_control_event
            if original_persist_control_event is not None else None
        ),
    )
    return protected, DataProtectionReport(redaction_counts=dict(counts))
