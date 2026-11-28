import hashlib

import pytest

from app.artifact_gateway import (
    ArtifactValidationError,
    build_object_key,
    inspect_upload,
    require_clean_scan,
)


def test_inspect_upload_accepts_pdf_and_computes_digest_and_size():
    payload = b"%PDF-1.7\nsmall synthetic document"
    result = inspect_upload(
        chunks=[payload[:8], payload[8:]],
        filename="Quarterly report.pdf",
        declared_media_type="application/pdf",
    )
    assert result.filename == "Quarterly report.pdf"
    assert result.media_type == "application/pdf"
    assert result.byte_size == len(payload)
    assert result.sha256 == hashlib.sha256(payload).hexdigest()
    assert result.content == payload


def test_inspect_upload_rejects_declared_type_that_disagrees_with_file_signature():
    with pytest.raises(ArtifactValidationError, match="does not match"):
        inspect_upload(
            chunks=[b"<html><script>alert(1)</script>"] ,
            filename="report.pdf",
            declared_media_type="application/pdf",
        )


def test_inspect_upload_rejects_path_traversal_and_control_characters():
    for filename in ("../secret.pdf", "folder/report.pdf", "bad\nname.pdf"):
        with pytest.raises(ArtifactValidationError):
            inspect_upload(
                chunks=[b"%PDF-1.4\nbody"],
                filename=filename,
                declared_media_type="application/pdf",
            )


def test_inspect_upload_enforces_streamed_byte_limit():
    with pytest.raises(ArtifactValidationError, match="maximum size"):
        inspect_upload(
            chunks=[b"%PDF-1.4\n", b"x" * 16],
            filename="large.pdf",
            declared_media_type="application/pdf",
            max_bytes=20,
        )


def test_inspect_upload_rejects_empty_and_unsupported_files():
    with pytest.raises(ArtifactValidationError, match="empty"):
        inspect_upload(chunks=[], filename="empty.pdf", declared_media_type="application/pdf")
    with pytest.raises(ArtifactValidationError, match="not allowed"):
        inspect_upload(chunks=[b"PK\x03\x04archive"], filename="bundle.zip", declared_media_type="application/zip")


def test_text_upload_requires_valid_utf8_without_binary_controls():
    with pytest.raises(ArtifactValidationError):
        inspect_upload(chunks=[b"hello\x00world"], filename="notes.txt", declared_media_type="text/plain")
    with pytest.raises(ArtifactValidationError):
        inspect_upload(chunks=[b"\xff\xfe"], filename="notes.txt", declared_media_type="text/plain")


def test_object_key_is_opaque_and_tenant_scoped_not_filename_derived():
    key = build_object_key(
        org_id="org-1", workspace_id="workspace-1", artifact_id="artifact-1"
    )
    assert key == "org-1/workspace-1/artifact-1"
    assert "report.pdf" not in key
    with pytest.raises(ValueError):
        build_object_key(org_id="../org", workspace_id="workspace-1", artifact_id="artifact-1")


def test_scan_gate_fails_closed_when_scanner_missing_or_not_clean():
    with pytest.raises(ArtifactValidationError, match="scanner is unavailable"):
        require_clean_scan(None)
    with pytest.raises(ArtifactValidationError, match="clean scan"):
        require_clean_scan({"status": "error", "scanner": "clam", "version": "1"})
    with pytest.raises(ArtifactValidationError, match="clean scan"):
        require_clean_scan({"status": "clean", "scanner": "", "version": "1"})
    assert require_clean_scan({"status": "clean", "scanner": "scanner", "version": "1"}) == ("scanner", "1")
