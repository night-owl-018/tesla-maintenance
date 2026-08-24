"""Attachment handling: receipts, photos and documents.

Files live under ``<config>/tesla_maintenance/attachments/service_<id>/`` so they
are captured by Home Assistant backups. Every filename is sanitised and every
resolved path is checked to stay inside the attachments root, which blocks
directory traversal via crafted names or symlinks.
"""

from __future__ import annotations

import logging
import mimetypes
import re
import shutil
import unicodedata
from pathlib import Path

from .const import (
    ALLOWED_ATTACHMENT_EXTENSIONS,
    ALLOWED_ATTACHMENT_MIME_TYPES,
    MAX_ATTACHMENT_BYTES,
)

_LOGGER = logging.getLogger(__name__)

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
_LEADING_DOTS = re.compile(r"^\.+")


class AttachmentError(Exception):
    """Raised when an attachment is rejected."""


def sanitize_filename(filename: str) -> str:
    """Return a safe, flat filename.

    Strips directory components, unicode tricks, and anything that is not a
    conservative filename character. Always returns a non-empty name.
    """
    # Take the final component only - defeats "../../etc/passwd" and "C:\x".
    candidate = filename.replace("\\", "/").split("/")[-1]
    candidate = unicodedata.normalize("NFKD", candidate)
    candidate = candidate.encode("ascii", "ignore").decode("ascii")
    candidate = _UNSAFE_CHARS.sub("_", candidate).strip("_")
    candidate = _LEADING_DOTS.sub("", candidate)
    if not candidate:
        candidate = "attachment"

    stem = Path(candidate).stem[:80] or "attachment"
    suffix = Path(candidate).suffix.lower()
    if suffix not in ALLOWED_ATTACHMENT_EXTENSIONS:
        raise AttachmentError(
            f"Unsupported file type '{suffix or 'none'}'. Allowed: "
            f"{', '.join(ALLOWED_ATTACHMENT_EXTENSIONS)}"
        )
    return f"{stem}{suffix}"


def guess_mime_type(filename: str) -> str:
    """Return the MIME type for a filename, validated against the allow list."""
    mime, _ = mimetypes.guess_type(filename)
    if mime == "image/jpg":  # some platforms report this non-standard value
        mime = "image/jpeg"
    if mime not in ALLOWED_ATTACHMENT_MIME_TYPES:
        raise AttachmentError(f"Unsupported MIME type: {mime or 'unknown'}")
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_ATTACHMENT_MIME_TYPES[mime]:
        raise AttachmentError(f"Extension {suffix} does not match MIME type {mime}")
    return mime


def record_directory(attachments_root: Path, service_record_id: int | None) -> Path:
    """Return the directory for a service record's attachments."""
    if service_record_id is None:
        return attachments_root / "unfiled"
    return attachments_root / f"service_{int(service_record_id):06d}"


def ensure_inside(root: Path, candidate: Path) -> Path:
    """Resolve ``candidate`` and confirm it stays inside ``root``."""
    root_resolved = root.resolve()
    resolved = candidate.resolve()
    if root_resolved != resolved and root_resolved not in resolved.parents:
        raise AttachmentError("Refusing to write outside the attachments directory")
    return resolved


def store_attachment(
    attachments_root: Path,
    source_path: str | Path,
    service_record_id: int | None,
    *,
    max_bytes: int = MAX_ATTACHMENT_BYTES,
) -> tuple[Path, str, int]:
    """Copy a file into the attachments store.

    Returns ``(stored_path, mime_type, size_bytes)``. Raises
    :class:`AttachmentError` if the file is missing, too large, or of an
    unsupported type.
    """
    source = Path(source_path)
    if not source.is_file():
        raise AttachmentError(f"Attachment source not found: {source}")

    size = source.stat().st_size
    if size > max_bytes:
        raise AttachmentError(
            f"Attachment is {size} bytes, which exceeds the {max_bytes} byte limit"
        )
    if size == 0:
        raise AttachmentError("Attachment is empty")

    filename = sanitize_filename(source.name)
    mime_type = guess_mime_type(filename)

    target_dir = record_directory(attachments_root, service_record_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = ensure_inside(attachments_root, target_dir / filename)

    # Never silently clobber an existing attachment.
    counter = 1
    while target.exists():
        stem, suffix = Path(filename).stem, Path(filename).suffix
        target = ensure_inside(attachments_root, target_dir / f"{stem}_{counter}{suffix}")
        counter += 1

    shutil.copy2(source, target)
    _LOGGER.debug("Stored attachment %s (%s bytes)", target.name, size)
    return target, mime_type, size


def delete_attachment_file(attachments_root: Path, stored_path: str | Path) -> bool:
    """Delete a stored attachment file, refusing paths outside the root."""
    try:
        resolved = ensure_inside(attachments_root, Path(stored_path))
    except AttachmentError:
        _LOGGER.warning("Refused to delete attachment outside the attachments root")
        return False
    if resolved.is_file():
        resolved.unlink()
        return True
    return False
