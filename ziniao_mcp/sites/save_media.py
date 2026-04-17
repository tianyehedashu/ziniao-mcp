"""Generic media-saving helpers for site presets.

Two layers of API:

1. **Atomic primitives** (reusable by any site / plugin / mode: ui step):

   - :func:`save_base64_as_file` — decode a base64 string and write it to disk,
     auto-detecting extension from the magic bytes.
   - :func:`download_url_to_file` — HTTP-GET a URL (e.g. GCS signed link, S3
     CloudFront) and write it to disk, extension from Content-Type or magic.

   Both accept a *prefix / stem path without extension* and return the
   **actual** :class:`Path` written (or ``None`` on failure). They are pure
   side-effect functions — no assumptions about the preset shape.

2. **High-level convention** — :func:`strip_and_save_encoded_images` expects the
   Google-Flow / Imagen-style ``images[]`` response contract (``encodedImage``
   or ``fifeUrl``) and is what ``--save-images`` drives.

New sites that return **non-image** binaries (CSV, zip, audio, PDF…) should
build their own glue on top of the two atomic primitives rather than reusing
:func:`strip_and_save_encoded_images`, which is deliberately image-biased.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


_MAGIC_EXT: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
    (b"%PDF-", ".pdf"),
    (b"PK\x03\x04", ".zip"),
    (b"ID3", ".mp3"),
    (b"\x1aE\xdf\xa3", ".webm"),
    (b"OggS", ".ogg"),
)


def _ext_from_magic(raw: bytes) -> str:
    for magic, ext in _MAGIC_EXT:
        if raw.startswith(magic):
            return ext
    if raw.startswith(b"RIFF") and len(raw) >= 12:
        if raw[8:12] == b"WEBP":
            return ".webp"
        if raw[8:12] == b"WAVE":
            return ".wav"
    return ".bin"


# Back-compat alias used by older callers / tests.
_image_ext_from_magic = _ext_from_magic


_CT_EXT: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/svg+xml": ".svg",
    "application/pdf": ".pdf",
    "application/zip": ".zip",
    "application/json": ".json",
    "text/csv": ".csv",
    "text/plain": ".txt",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
}


def _ext_from_content_type(ct: str) -> str:
    ct = ct.lower().split(";")[0].strip()
    return _CT_EXT.get(ct, ".bin")


def _normalize_stem(dest: str | Path) -> tuple[Path, str]:
    """Split *dest* into (parent dir, filename stem). Creates parent dir."""
    base = Path(dest).expanduser()
    parent = base.parent
    if str(parent) not in ("", "."):
        parent.mkdir(parents=True, exist_ok=True)
    return parent, base.name


def save_base64_as_file(b64: str, dest_no_ext: str | Path) -> Path | None:
    """Decode a base64 payload and write it to ``<dest_no_ext><autoext>``.

    Returns the actual :class:`Path` written, or ``None`` on decode failure.
    Extension is inferred from magic bytes (``.png``/``.jpg``/``.pdf``/…, fallback ``.bin``).
    """
    if not isinstance(b64, str) or not b64.strip():
        return None
    try:
        raw = base64.b64decode(b64.strip())
    except (ValueError, TypeError):
        log.warning("save_base64_as_file: invalid base64 (len=%d)", len(b64))
        return None
    parent, stem = _normalize_stem(dest_no_ext)
    path = parent / f"{stem}{_ext_from_magic(raw)}"
    path.write_bytes(raw)
    return path


def download_url_to_file(
    url: str,
    dest_no_ext: str | Path,
    *,
    timeout: float = 30,
    headers: dict[str, str] | None = None,
) -> Path | None:
    """HTTP-GET *url* and write bytes to ``<dest_no_ext><autoext>``.

    Extension priority: Content-Type → magic bytes → ``.bin``. Returns the
    actual :class:`Path` on HTTP 200, ``None`` otherwise (non-200, network
    error, invalid URL). Uses ``httpx`` with ``follow_redirects=True``.
    """
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return None
    try:
        import httpx  # pylint: disable=import-outside-toplevel

        resp = httpx.get(url, follow_redirects=True, timeout=timeout, headers=headers)
        if resp.status_code != 200:
            log.warning("download_url_to_file %s -> HTTP %s", url[:60], resp.status_code)
            return None
        raw = resp.content
        ct = resp.headers.get("content-type", "")
        ext = _ext_from_content_type(ct) if ct else ""
        if ext in ("", ".bin"):
            ext = _ext_from_magic(raw)
        parent, stem = _normalize_stem(dest_no_ext)
        path = parent / f"{stem}{ext}"
        path.write_bytes(raw)
        return path
    except Exception:  # noqa: BLE001
        log.exception("download_url_to_file failed: %s", url[:80])
        return None


def _download_fife_url(url: str, dest: Path, *, timeout: float = 30) -> bool:
    """Legacy wrapper kept for backward compatibility. Prefer :func:`download_url_to_file`.

    *dest* is the intended path **with** a placeholder suffix (``.bin``); the
    real extension is resolved from Content-Type/magic. Returns ``True`` on
    success and leaves the file at the resolved path (caller can glob to find
    it).
    """
    stem_path = dest.with_suffix("") if dest.suffix else dest
    written = download_url_to_file(url, stem_path, timeout=timeout)
    return written is not None


def strip_and_save_encoded_images(result: dict[str, Any], prefix: str) -> dict[str, Any]:
    """Save ``images[]`` to files under *prefix* and replace bulky data with short notes.

    Handles two formats:
    - ``encodedImage`` (base64): decode and write.
    - ``fifeUrl`` (GCS signed URL): HTTP GET and write.

    *prefix* is a path **without** extension, e.g. ``exports/flow-mountain`` writes
    ``exports/flow-mountain-0.png``, ``exports/flow-mountain-1.jpg``, …

    Returns a **shallow-copied** result dict (images list is copied per item).
    """
    images = result.get("images")
    if not isinstance(images, list) or not prefix.strip():
        return result

    parent, stem = _normalize_stem(prefix)

    out: dict[str, Any] = {**result, "images": []}
    saved: list[str] = []

    for idx, im in enumerate(images):
        if not isinstance(im, dict):
            out["images"].append(im)
            continue
        item = dict(im)

        b64 = item.get("encodedImage")
        if isinstance(b64, str) and b64.strip():
            written = save_base64_as_file(b64, parent / f"{stem}-{idx}")
            if written is not None:
                saved.append(str(written.resolve()))
                item["encodedImage"] = f"[saved: {written.name}]"
            else:
                item["encodedImage"] = "[invalid base64]"

        fife = item.get("fifeUrl")
        if isinstance(fife, str) and fife.startswith("http"):
            written = download_url_to_file(fife, parent / f"{stem}-{idx}")
            if written is not None:
                saved.append(str(written.resolve()))
                item["fifeUrl"] = f"[saved: {written.name}]"

        out["images"].append(item)

    if saved:
        out["_saved_image_paths"] = saved
    return out


__all__ = [
    "save_base64_as_file",
    "download_url_to_file",
    "strip_and_save_encoded_images",
]
