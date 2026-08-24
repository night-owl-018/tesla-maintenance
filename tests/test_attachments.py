"""Tests for attachment validation and storage."""

from __future__ import annotations

import pytest
from custom_components.tesla_maintenance.attachments import (
    AttachmentError,
    delete_attachment_file,
    ensure_inside,
    guess_mime_type,
    record_directory,
    sanitize_filename,
    store_attachment,
)


def test_sanitize_strips_directory_components():
    assert sanitize_filename("../../etc/passwd.pdf") == "passwd.pdf"
    assert sanitize_filename("/absolute/path/receipt.pdf") == "receipt.pdf"
    assert sanitize_filename(r"C:\Windows\evil.png") == "evil.png"


def test_sanitize_replaces_unsafe_characters():
    assert sanitize_filename("my receipt (2026);rm -rf.pdf") == "my_receipt_2026_rm_-rf.pdf"


def test_sanitize_rejects_unsupported_extensions():
    for name in ("script.sh", "payload.exe", "notes.txt", "archive.zip", "noext"):
        with pytest.raises(AttachmentError):
            sanitize_filename(name)


def test_sanitize_rejects_hidden_and_empty_names():
    with pytest.raises(AttachmentError):
        sanitize_filename("...")


def test_guess_mime_type_allows_supported_types():
    assert guess_mime_type("receipt.pdf") == "application/pdf"
    assert guess_mime_type("photo.jpg") == "image/jpeg"
    assert guess_mime_type("photo.jpeg") == "image/jpeg"
    assert guess_mime_type("photo.png") == "image/png"
    assert guess_mime_type("photo.webp") == "image/webp"


def test_guess_mime_type_rejects_others():
    with pytest.raises(AttachmentError):
        guess_mime_type("malware.exe")


def test_record_directory_naming(tmp_path):
    assert record_directory(tmp_path, 1).name == "service_000001"
    assert record_directory(tmp_path, None).name == "unfiled"


def test_ensure_inside_blocks_escape(tmp_path):
    root = tmp_path / "attachments"
    root.mkdir()
    ensure_inside(root, root / "service_000001" / "a.pdf")
    with pytest.raises(AttachmentError):
        ensure_inside(root, tmp_path / "elsewhere" / "a.pdf")


def test_store_attachment_copies_and_reports_metadata(tmp_path):
    root = tmp_path / "attachments"
    source = tmp_path / "receipt.pdf"
    source.write_bytes(b"%PDF-1.4 test")

    stored, mime, size = store_attachment(root, source, 1)
    assert stored.exists()
    assert stored.parent.name == "service_000001"
    assert mime == "application/pdf"
    assert size == len(b"%PDF-1.4 test")


def test_store_attachment_does_not_clobber(tmp_path):
    root = tmp_path / "attachments"
    source = tmp_path / "receipt.pdf"
    source.write_bytes(b"data")

    first, _, _ = store_attachment(root, source, 1)
    second, _, _ = store_attachment(root, source, 1)
    assert first != second
    assert second.name == "receipt_1.pdf"


def test_store_attachment_rejects_traversal_name(tmp_path):
    root = tmp_path / "attachments"
    outside = tmp_path / "secret"
    outside.mkdir()
    source = outside / "passwd.pdf"
    source.write_bytes(b"data")

    stored, _, _ = store_attachment(root, source, 1)
    # The file is copied inside the attachments root, never referenced in place.
    assert root.resolve() in stored.resolve().parents


def test_store_attachment_rejects_oversized_and_empty(tmp_path):
    root = tmp_path / "attachments"
    big = tmp_path / "big.png"
    big.write_bytes(b"x" * 100)
    with pytest.raises(AttachmentError):
        store_attachment(root, big, 1, max_bytes=10)

    empty = tmp_path / "empty.png"
    empty.write_bytes(b"")
    with pytest.raises(AttachmentError):
        store_attachment(root, empty, 1)


def test_store_attachment_rejects_missing_file(tmp_path):
    with pytest.raises(AttachmentError):
        store_attachment(tmp_path / "attachments", tmp_path / "nope.pdf", 1)


def test_delete_attachment_file_refuses_outside_root(tmp_path):
    root = tmp_path / "attachments"
    root.mkdir()
    outside = tmp_path / "important.pdf"
    outside.write_bytes(b"data")

    assert delete_attachment_file(root, outside) is False
    assert outside.exists()


def test_delete_attachment_file_removes_stored_file(tmp_path):
    root = tmp_path / "attachments"
    source = tmp_path / "receipt.pdf"
    source.write_bytes(b"data")
    stored, _, _ = store_attachment(root, source, 2)

    assert delete_attachment_file(root, stored) is True
    assert not stored.exists()
