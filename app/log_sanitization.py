"""Central redaction for application and worker log records.

Logs are an operational surface, not a data store. Secret-bearing messages are
replaced wholesale; supported PII is redacted before handlers format records.
"""
from __future__ import annotations

import logging
import re
import threading
import traceback
from typing import Any

from app.data_protection import DataProtectionBlocked, sanitize_text

_SENSITIVE_FIELD = re.compile(
    r"(?:authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"client[_-]?secret|password|passwd|credential|cookie|session[_-]?id|"
    r"email|phone|mobile|address|aadhaar|pan|ssn|card[_-]?number)",
    re.IGNORECASE,
)
_REDACTED = "[REDACTED]"
_REDACTED_VALUE = "[REDACTED_SENSITIVE_LOG_VALUE]"
_REDACTED_FIELD = "[REDACTED_NON_SCALAR_LOG_FIELD]"
_LOCK = threading.Lock()
_CONFIGURED = False
_ORIGINAL_FACTORY = None
_ORIGINAL_MAKE_RECORD = None
_STANDARD_FIELDS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


def _redact_text(value: str) -> str:
    try:
        cleaned, _ = sanitize_text(value)
        return cleaned
    except DataProtectionBlocked:
        return _REDACTED_VALUE


def _redact_extra(value: Any, *, depth: int = 0) -> Any:
    if depth > 5:
        return _REDACTED_FIELD
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            safe_key = _redact_text(str(key))
            if _SENSITIVE_FIELD.search(str(key)):
                cleaned[safe_key] = _REDACTED
            else:
                cleaned[safe_key] = _redact_extra(item, depth=depth + 1)
        return cleaned
    if isinstance(value, list):
        return [_redact_extra(item, depth=depth + 1) for item in value[:100]]
    if isinstance(value, tuple):
        return tuple(_redact_extra(item, depth=depth + 1) for item in value[:100])
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _REDACTED_FIELD


def _sanitize_record(record: logging.LogRecord) -> logging.LogRecord:
    try:
        rendered = record.getMessage()
    except Exception:
        rendered = "[REDACTED_UNFORMATTABLE_LOG_MESSAGE]"
    record.msg = _redact_text(rendered)
    record.args = ()

    if record.exc_info:
        try:
            exception_text = "".join(traceback.format_exception(*record.exc_info))
        except Exception:
            exception_text = "[REDACTED_EXCEPTION_DETAILS]"
        record.exc_text = _redact_text(exception_text)
        record.exc_info = None

    if record.stack_info:
        record.stack_info = _redact_text(record.stack_info)

    for key, value in tuple(record.__dict__.items()):
        if key in _STANDARD_FIELDS or key in {"exc_info", "exc_text", "stack_info"}:
            continue
        if _SENSITIVE_FIELD.search(key):
            record.__dict__[key] = _REDACTED
        elif isinstance(value, (str, dict, list, tuple)):
            record.__dict__[key] = _redact_extra(value)
        elif not (value is None or isinstance(value, (bool, int, float))):
            record.__dict__[key] = _REDACTED_FIELD
    return record


def configure_log_redaction() -> None:
    """Install an idempotent LogRecord factory so future handlers are covered."""
    global _CONFIGURED, _ORIGINAL_FACTORY, _ORIGINAL_MAKE_RECORD
    if _CONFIGURED:
        return
    with _LOCK:
        if _CONFIGURED:
            return
        _ORIGINAL_FACTORY = logging.getLogRecordFactory()
        original_factory = _ORIGINAL_FACTORY

        def redacting_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
            return _sanitize_record(original_factory(*args, **kwargs))

        logging.setLogRecordFactory(redacting_factory)
        _ORIGINAL_MAKE_RECORD = logging.Logger.makeRecord
        original_make_record = _ORIGINAL_MAKE_RECORD

        def redacting_make_record(self, *args: Any, **kwargs: Any) -> logging.LogRecord:
            # Logger.makeRecord attaches `extra` fields after the LogRecord
            # factory runs, so sanitize once more after those fields exist.
            return _sanitize_record(original_make_record(self, *args, **kwargs))

        logging.Logger.makeRecord = redacting_make_record
        _CONFIGURED = True
