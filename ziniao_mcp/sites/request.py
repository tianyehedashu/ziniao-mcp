"""Request-spec preparation and response persistence.

- :func:`prepare_request` merges preset / file / CLI args into one unified
  spec dict (applying ``header_inject`` / var rendering / UI validation
  / plugin ``before_fetch``).
- :func:`save_response_body` writes a fetched body to disk, handling raw
  bytes, declared decode encodings and JSON pretty-printing.
- Body-byte helpers (:func:`parse_charset`, :func:`decode_body_bytes`,
  :func:`coerce_page_fetch_eval_result`) normalise values returned from the
  browser-side ``fetch``/``js`` wrappers.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from ._base import SitePlugin
from .discovery import load_preset
from .plugin_loader import get_plugin
from .rendering import render_vars
from .validation import _validate_ui_preset
from .variables import resolve_text_file_ref


def parse_charset(content_type: str) -> str:
    """Extract ``charset=…`` from a Content-Type header value.

    Returns the normalised codec name, or ``""`` if absent.
    """
    for part in content_type.split(";"):
        part = part.strip()
        if part.lower().startswith("charset="):
            return part[8:].strip().strip("\"'")
    return ""


def decode_body_bytes(raw: bytes, content_type: str) -> str:
    """Decode raw response bytes to a Python string.

    Strategy: honour ``charset`` from *content_type* first, then try strict
    UTF-8, and finally fall back to ``utf-8`` with replacement characters so
    that callers always receive a valid ``str``.
    """
    charset = parse_charset(content_type)
    if charset:
        try:
            return raw.decode(charset)
        except (UnicodeDecodeError, LookupError):
            pass
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")


def coerce_page_fetch_eval_result(result: Any) -> dict[str, Any]:
    """Normalize ``tab.evaluate`` return from fetch/js wrappers into a page_fetch dict."""
    if not isinstance(result, str):
        return {"ok": True, "body": str(result) if result else ""}
    try:
        parsed = json.loads(result)
    except (json.JSONDecodeError, TypeError):
        return {"ok": True, "body": result}
    if isinstance(parsed, dict) and "body_b64" in parsed:
        raw = base64.b64decode(parsed["body_b64"])
        ct = parsed.get("content_type", "")
        body_str = decode_body_bytes(raw, ct)
        return {
            "ok": True,
            "status": parsed.get("status"),
            "statusText": parsed.get("statusText", ""),
            "body": body_str,
            "body_b64": parsed["body_b64"],
            "content_type": ct,
        }
    if isinstance(parsed, dict):
        return {"ok": True, **parsed}
    return {"ok": True, "body": result}


def prepare_request(
    *,
    preset: str = "",
    file: str = "",
    script: str = "",
    url: str = "",
    method: str = "GET",
    body: str = "",
    headers: dict | None = None,
    header_inject: list[dict] | None = None,
    var_values: dict[str, str] | None = None,
) -> tuple[dict, SitePlugin | None]:
    """Build a unified request spec from preset / file / CLI args.

    ``header_inject`` validation is applied in ``dispatch._page_fetch``,
    not here.

    Returns ``(spec_dict, plugin_or_None)``.
    Raises ``FileNotFoundError`` / ``ValueError`` / ``json.JSONDecodeError``.
    """
    spec: dict = {}
    plugin: SitePlugin | None = None
    site_name = ""

    if preset:
        spec = load_preset(preset)
        site_name = preset.split("/")[0] if "/" in preset else preset
        plugin = get_plugin(site_name)
    elif file:
        spec = json.loads(Path(file).read_text(encoding="utf-8"))

    if spec.get("mode") == "ui":
        _validate_ui_preset(spec)

    merged_input = dict(var_values or {})
    merged_for_plugin: dict[str, str] = {}
    if spec.get("vars"):
        var_defs = spec["vars"]
        defaults = {k: v["default"] for k, v in var_defs.items() if "default" in v}
        merged_for_plugin = {
            k: resolve_text_file_ref(v)
            for k, v in {**defaults, **merged_input}.items()
        }
        for k, vdef in var_defs.items():
            if vdef.get("required") and k not in merged_for_plugin:
                if vdef.get("type") == "secret" and vdef.get("source"):
                    continue
                raise ValueError(f"Required variable missing: {k}")
        spec = render_vars(spec, merged_input)
        spec["_ziniao_merged_vars"] = merged_for_plugin

    cli_output_decode = spec.pop("output_decode_encoding", None)

    if script:
        spec["mode"] = "js"
        spec["script"] = script
    if url:
        spec["url"] = url
    if method != "GET" or "method" not in spec:
        spec.setdefault("method", method)
    if method != "GET":
        spec["method"] = method
    if body:
        try:
            spec["body"] = json.loads(body)
        except json.JSONDecodeError:
            spec["body"] = body
    if headers:
        existing = spec.get("headers") or {}
        existing.update(headers)
        spec["headers"] = existing
    if header_inject:
        spec["header_inject"] = header_inject

    if isinstance(spec.get("body"), (dict, list)):
        spec["body"] = json.dumps(spec["body"], ensure_ascii=False)

    if plugin:
        spec = plugin.before_fetch(spec)

    if spec.get("mode") != "ui":
        spec.pop("_ziniao_merged_vars", None)
    if cli_output_decode:
        spec["_ziniao_output_decode_encoding"] = cli_output_decode

    return spec, plugin


def save_response_body(
    body_text: str,
    output_path: str,
    *,
    body_b64: str = "",
    content_type: str = "",
    output_encoding: str = "",
    decode_encoding: str = "",
) -> str:
    """Write response body to *output_path*.

    When *body_b64* is present and neither *decode_encoding* nor *output_encoding*
    is set: if raw bytes are **strict UTF-8**, write a UTF-8 text file (JSON is
    pretty-printed when valid); otherwise write **raw bytes** unchanged (e.g.
    CP932 CSV — use ``--decode-encoding cp932`` to get a UTF-8 file).

    If *decode_encoding* is set (e.g. ``"cp932"`` for Rakuten CSV), raw bytes
    are decoded with that codec and written as text; the file encoding is
    *output_encoding* or ``utf-8``.  Use this when the server omits charset
    in ``Content-Type`` but the body is not UTF-8.

    If only *output_encoding* is given (no *decode_encoding*), raw bytes are
    decoded via ``Content-Type`` charset / UTF-8 (:func:`decode_body_bytes`),
    then re-encoded; JSON pretty-printing is attempted when valid.

    Falls back to the legacy ``body_text`` path when *body_b64* is absent
    (e.g. merged pagination results that are already UTF-8 JSON).

    Returns a human-readable confirmation message.
    """
    dest = Path(output_path)

    if body_b64:
        raw = base64.b64decode(body_b64)
        if decode_encoding:
            text = raw.decode(decode_encoding)
            try:
                parsed = json.loads(text)
                text = json.dumps(parsed, ensure_ascii=False, indent=2)
            except (json.JSONDecodeError, TypeError):
                pass
            enc = output_encoding or "utf-8"
            dest.write_text(text, encoding=enc)
            return f"Saved to {output_path} ({len(text)} chars, {decode_encoding} → {enc})"
        if output_encoding:
            text = decode_body_bytes(raw, content_type)
            try:
                parsed = json.loads(text)
                text = json.dumps(parsed, ensure_ascii=False, indent=2)
            except (json.JSONDecodeError, TypeError):
                pass
            dest.write_text(text, encoding=output_encoding)
            return f"Saved to {output_path} ({len(text)} chars, {output_encoding})"
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            dest.write_bytes(raw)
            return f"Saved to {output_path} ({len(raw)} bytes)"
        try:
            parsed = json.loads(text)
            pretty = json.dumps(parsed, ensure_ascii=False, indent=2)
            dest.write_text(pretty, encoding="utf-8")
            return f"Saved to {output_path} ({len(pretty)} chars, JSON pretty-printed)"
        except (json.JSONDecodeError, TypeError):
            pass
        dest.write_text(text, encoding="utf-8")
        return f"Saved to {output_path} ({len(text)} chars, utf-8)"

    try:
        parsed = json.loads(body_text)
        body_text = json.dumps(parsed, ensure_ascii=False, indent=2)
    except (json.JSONDecodeError, TypeError):
        pass
    dest.write_text(body_text, encoding=output_encoding or "utf-8")
    return f"Saved to {output_path} ({len(body_text)} chars)"
