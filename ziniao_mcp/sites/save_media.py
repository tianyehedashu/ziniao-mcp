"""Generic media-saving helpers for site presets.

Three layers of API, all site-agnostic:

1. **Atomic primitives** (reusable by any site / plugin / mode: ui step):

   - :func:`save_base64_as_file` — decode a base64 string and write it to disk,
     auto-detecting extension from the magic bytes.
   - :func:`download_url_to_file` — HTTP-GET a URL (e.g. GCS signed link, S3
     CloudFront) and write it to disk, extension from Content-Type or magic.

   Both accept a *prefix / stem path without extension* and return the
   **actual** :class:`Path` written (or ``None`` on failure). They are pure
   side-effect functions — no assumptions about the preset shape.

2. **Declarative compiler** — :func:`compile_media_contract` turns the
   ``media_contract`` block from a preset JSON into the item list expected
   by :func:`apply_media_contract`.  This is what the default
   :meth:`SitePlugin.media_contract` dispatches to, so JSON-only sites get
   ``--save-images`` support with zero Python code.

3. **Generic orchestrator** — :func:`apply_media_contract` consumes the list
   returned by :meth:`SitePlugin.media_contract` and performs the writes,
   patches the response with short ``"[saved: <name>]"`` notes and collects
   saved paths under ``result["_saved_image_paths"]``.  Site-specific field
   names (``encodedImage`` / ``fifeUrl`` / ``artifacts`` / ``b64_json`` …)
   live in each *plugin* (or the preset JSON), **not** in this module.
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


def _deep_copy_for_patch(result: dict[str, Any], paths: list[list[Any]]) -> dict[str, Any]:
    """Return a copy of *result* where every container on any patch *paths* is cloned.

    Unpatched branches stay shared (cheap); patched branches are isolated so the
    caller can mutate without leaking into the original dict.
    """
    if not paths:
        return result
    root: Any = dict(result) if isinstance(result, dict) else list(result)

    for path in paths:
        cur = root
        for step in path[:-1]:
            nxt = cur[step]
            if isinstance(nxt, dict):
                cloned: Any = dict(nxt)
            elif isinstance(nxt, list):
                cloned = list(nxt)
            else:
                break
            cur[step] = cloned
            cur = cloned
    return root


def _set_at_path(obj: Any, path: list[Any], value: Any) -> None:
    cur = obj
    for step in path[:-1]:
        cur = cur[step]
    cur[path[-1]] = value


def apply_media_contract(
    result: dict[str, Any],
    items: list[dict],
    prefix: str,
) -> dict[str, Any]:
    """Persist media items declared by :meth:`SitePlugin.media_contract`.

    *items* is the list returned by ``plugin.media_contract(result)``.  Each
    item tells us **what** to save (base64 / url), **how to name** it
    (stem_suffix) and **where in result to patch** with a short note.

    *prefix* is a stem path without extension; the actual extension is
    inferred from magic bytes / Content-Type by the atomic primitives.

    Returns a new result dict (shallow-copied along patched paths).  Saved
    file paths are collected into ``result["_saved_image_paths"]`` — the key
    name is historical; it accepts arbitrary media types.
    """
    if not items or not prefix.strip():
        return result

    parent, stem = _normalize_stem(prefix)

    paths: list[list[Any]] = [list(it.get("path") or []) for it in items]
    out = _deep_copy_for_patch(result, paths)
    saved: list[str] = []

    for item in items:
        source = item.get("source")
        value = item.get("value")
        suffix = str(item.get("stem_suffix") or "")
        path = list(item.get("path") or [])
        dest = parent / f"{stem}{suffix}"

        if source == "base64" and isinstance(value, str):
            written = save_base64_as_file(value, dest)
            if written is not None:
                saved.append(str(written.resolve()))
                if path:
                    _set_at_path(out, path, f"[saved: {written.name}]")
            elif path:
                _set_at_path(out, path, "[invalid base64]")
        elif source == "url" and isinstance(value, str):
            written = download_url_to_file(value, dest)
            if written is not None:
                saved.append(str(written.resolve()))
                if path:
                    _set_at_path(out, path, f"[saved: {written.name}]")

    if saved:
        out["_saved_image_paths"] = saved
    return out


_VALID_SOURCES = frozenset({"base64", "url"})


def _walk_dotted(obj: Any, path: str) -> tuple[Any, list[Any]]:
    """Follow a ``a.b.c`` / ``a.0.b`` dotted path through *obj*.

    Returns ``(value, concrete_keys)`` where ``concrete_keys`` is the list
    of dict keys / list indices actually traversed (suitable for
    :func:`_set_at_path`).  Purely numeric segments (``0``, ``-1``, …)
    dereference a list by index.  If any segment is missing or hits a
    non-container, returns ``(None, [])`` so the caller skips the rule
    quietly.
    """
    if not isinstance(path, str):
        return None, []
    parts = [p for p in path.split(".") if p]
    if not parts:
        return None, []
    cur: Any = obj
    keys: list[Any] = []
    for segment in parts:
        if isinstance(cur, dict) and segment in cur:
            cur = cur[segment]
            keys.append(segment)
        elif isinstance(cur, list) and segment.lstrip("-").isdigit():
            idx = int(segment)
            if -len(cur) <= idx < len(cur):
                cur = cur[idx]
                keys.append(idx)
            else:
                return None, []
        else:
            return None, []
    return cur, keys


def _format_suffix(template: str, *, idx: int | None = None, field: str | None = None) -> str:
    """Fill ``{idx}`` / ``{field}`` placeholders in *template* (best-effort).

    Unknown placeholders are left as-is so users can diagnose typos
    instead of silently getting an odd filename.
    """
    out = str(template or "")
    if idx is not None:
        out = out.replace("{idx}", str(idx))
    if field is not None:
        out = out.replace("{field}", field)
    return out


def _compile_list_rule(rule: dict, result: dict) -> list[dict]:
    target, base_keys = _walk_dotted(result, str(rule.get("items_at") or ""))
    if not isinstance(target, list):
        return []
    fields = rule.get("fields")
    if not isinstance(fields, list) or not fields:
        return []

    multi_field = len(fields) > 1
    default_tmpl = "-{idx}-{field}" if multi_field else "-{idx}"
    stem_tmpl = str(rule.get("stem_suffix") or default_tmpl)
    if multi_field and "{field}" not in stem_tmpl:
        raise ValueError(
            f"media_contract rule items_at={rule.get('items_at')!r} declares "
            f"{len(fields)} fields but stem_suffix={stem_tmpl!r} lacks the "
            f"'{{field}}' placeholder — generated file names would collide and "
            f"one of them would silently overwrite the other. Either split "
            f"the rule per field or include '{{field}}' in the template."
        )

    items: list[dict] = []
    for idx, elem in enumerate(target):
        if not isinstance(elem, dict):
            continue
        for fdef in fields:
            if not isinstance(fdef, dict):
                continue
            key = str(fdef.get("key") or "").strip()
            source = str(fdef.get("source") or "").strip()
            if not key or source not in _VALID_SOURCES:
                continue
            val = elem.get(key)
            if not isinstance(val, str) or not val.strip():
                continue
            if source == "url" and not val.startswith(("http://", "https://")):
                continue
            items.append({
                "source": source,
                "value": val,
                "stem_suffix": _format_suffix(stem_tmpl, idx=idx, field=key),
                "path": [*base_keys, idx, key],
            })
    return items


def _compile_single_rule(rule: dict, result: dict) -> list[dict]:
    path_str = str(rule.get("at") or "").strip()
    source = str(rule.get("source") or "").strip()
    if not path_str or source not in _VALID_SOURCES:
        return []
    val, keys = _walk_dotted(result, path_str)
    if not isinstance(val, str) or not val.strip():
        return []
    if source == "url" and not val.startswith(("http://", "https://")):
        return []
    last_field = keys[-1] if keys else ""
    return [{
        "source": source,
        "value": val,
        "stem_suffix": _format_suffix(str(rule.get("stem_suffix") or ""), field=last_field),
        "path": list(keys),
    }]


def compile_media_contract(rules: Any, result: dict) -> list[dict]:
    """Compile the preset JSON ``media_contract`` block into save items.

    Two rule shapes are supported (mix freely in one list):

    - **List rule** — iterate a list and grab one or more media fields per
      element::

          { "items_at": "images",
            "fields": [
              { "key": "encodedImage", "source": "base64" },
              { "key": "fifeUrl",      "source": "url" }
            ],
            "stem_suffix": "-{idx}" }

    - **Single rule** — pick one specific field anywhere in the response::

          { "at": "thumbnail_url",
            "source": "url",
            "stem_suffix": "-thumb" }

    ``stem_suffix`` supports ``{idx}`` (list element index) and
    ``{field}`` (field key) placeholders.

    Unknown / malformed rules are silently skipped so one bad entry in a
    large contract doesn't kill the whole ``--save-images`` run.  Returns
    ``[]`` when *rules* is anything other than a non-empty list.
    """
    if not isinstance(rules, list) or not rules:
        return []
    if not isinstance(result, dict):
        return []
    items: list[dict] = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        if "items_at" in rule:
            items.extend(_compile_list_rule(rule, result))
        elif "at" in rule:
            items.extend(_compile_single_rule(rule, result))
    return items


__all__ = [
    "apply_media_contract",
    "compile_media_contract",
    "download_url_to_file",
    "save_base64_as_file",
]
