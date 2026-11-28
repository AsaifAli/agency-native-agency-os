"""Fail-closed primitives for bounded artifact ingestion.

This module deliberately does not expose an upload API or choose a storage/scanner
provider. It validates bytes before any provider adapter is allowed to persist them.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Mapping


DEFAULT_MAX_ARTIFACT_BYTES = 20 * 1024 * 1024
_ALLOWED_TYPES = {
    "application/pdf": {".pdf"},
    "image/png": {".png"},
    "image/jpeg": {".jpg", ".jpeg"},
    "text/plain": {".txt"},
    "text/csv": {".csv"},
}
_SEGMENT = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class ArtifactValidationError(ValueError):
    """The artifact is unsafe, malformed, or cannot be verified."""


@dataclass(frozen=True)
class InspectedUpload:
    filename: str
    media_type: str
    byte_size: int
    sha256: str
    content: bytes


def _safe_filename(filename: str, media_type: str) -> str:
    if not isinstance(filename, str) or not filename or len(filename) > 255:
        raise ArtifactValidationError("filename is required and must be at most 255 characters")
    normalized = unicodedata.normalize("NFC", filename)
    if normalized in {".", ".."} or "/" in normalized or "\\" in normalized:
        raise ArtifactValidationError("filename must not contain path components")
    if any(unicodedata.category(char).startswith("C") for char in normalized):
        raise ArtifactValidationError("filename contains control or formatting characters")
    if normalized.startswith(".") or normalized.endswith(".") or normalized.strip() != normalized:
        raise ArtifactValidationError("filename is not a safe plain filename")
    suffix = "." + normalized.rsplit(".", 1)[-1].lower() if "." in normalized else ""
    if suffix not in _ALLOWED_TYPES[media_type]:
        raise ArtifactValidationError("filename extension does not match declared media type")
    return normalized


def _verify_signature(content: bytes, media_type: str) -> None:
    if media_type == "application/pdf":
        valid = content.startswith(b"%PDF-")
    elif media_type == "image/png":
        valid = content.startswith(b"\x89PNG\r\n\x1a\n") and len(content) >= 24 and content[12:16] == b"IHDR"
    elif media_type == "image/jpeg":
        valid = content.startswith(b"\xff\xd8\xff") and content.endswith(b"\xff\xd9")
    else:
        try:
            content.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ArtifactValidationError("text artifact must be valid UTF-8") from exc
        if b"\x00" in content:
            raise ArtifactValidationError("text artifact contains binary control bytes")
        valid = all(byte in (9, 10, 13) or byte >= 32 for byte in content)
    if not valid:
        raise ArtifactValidationError("file signature does not match declared media type")


def inspect_upload(
    *,
    chunks: Iterable[bytes],
    filename: str,
    declared_media_type: str,
    max_bytes: int = DEFAULT_MAX_ARTIFACT_BYTES,
) -> InspectedUpload:
    """Read a bounded stream, validate its declared type against its bytes, and hash it."""
    if max_bytes < 1 or max_bytes > 100 * 1024 * 1024:
        raise ValueError("max_bytes must be between 1 byte and 100 MiB")
    media_type = (declared_media_type or "").split(";", 1)[0].strip().lower()
    if media_type not in _ALLOWED_TYPES:
        raise ArtifactValidationError("declared media type is not allowed")
    safe_name = _safe_filename(filename, media_type)
    buffer = bytearray()
    digest = hashlib.sha256()
    for chunk in chunks:
        if not isinstance(chunk, (bytes, bytearray, memoryview)):
            raise ArtifactValidationError("upload stream yielded a non-byte chunk")
        if not chunk:
            continue
        if len(buffer) + len(chunk) > max_bytes:
            raise ArtifactValidationError("artifact exceeds maximum size")
        buffer.extend(chunk)
        digest.update(chunk)
    if not buffer:
        raise ArtifactValidationError("artifact is empty")
    content = bytes(buffer)
    _verify_signature(content, media_type)
    return InspectedUpload(
        filename=safe_name,
        media_type=media_type,
        byte_size=len(content),
        sha256=digest.hexdigest(),
        content=content,
    )


def build_object_key(*, org_id: str, workspace_id: str, artifact_id: str) -> str:
    """Build a tenant-scoped opaque key; caller IDs must be server-generated identifiers."""
    for value in (org_id, workspace_id, artifact_id):
        if not isinstance(value, str) or not _SEGMENT.fullmatch(value):
            raise ValueError("object key identifiers must be safe opaque path segments")
    return f"{org_id}/{workspace_id}/{artifact_id}"


def require_clean_scan(result: Mapping[str, str] | None) -> tuple[str, str]:
    """Return scanner identity only for an explicit clean result; all other states fail closed."""
    if result is None:
        raise ArtifactValidationError("malware scanner is unavailable; upload remains quarantined")
    status = result.get("status", "").strip().lower()
    scanner = result.get("scanner", "").strip()
    version = result.get("version", "").strip()
    if status != "clean" or not scanner or not version:
        raise ArtifactValidationError("artifact requires an explicit clean scan and scanner version")
    return scanner, version
