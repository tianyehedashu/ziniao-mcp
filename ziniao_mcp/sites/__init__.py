"""Site preset discovery, loading, and variable rendering.

Discovery order (same preset ID → first match wins):
1. User-local  ``~/.ziniao/sites/<site>/<preset>.json``
2. entry_points group ``ziniao.sites`` (pip-installed third-party)
3. Built-in    ``ziniao_mcp/sites/<site>/<preset>.json``

Optional JSON fields on presets:

- ``auth``: ``{ "type": "cookie"|"xsrf"|"token"|"none", "hint": "..." }``
- ``pagination``: ``body_field`` / ``offset`` config for ``--all`` (see built-in examples).
"""

from __future__ import annotations

import asyncio
import copy
import json
import re
from pathlib import Path
from typing import Any, Callable

from ._base import SitePlugin  # noqa: F401 — re-export for convenience

BUILTIN_DIR = Path(__file__).parent
USER_DIR = Path.home() / ".ziniao" / "sites"

_SKIP_DIRS = {"__pycache__"}
_VAR_RE = re.compile(r"\{\{(\w+)\}\}")


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def _scan_dir(base: Path) -> dict[str, Path]:
    """Return ``{preset_id: json_path}`` for all ``<site>/<name>.json`` under *base*."""
    result: dict[str, Path] = {}
    if not base.is_dir():
        return result
    for site_dir in sorted(base.iterdir()):
        if not site_dir.is_dir() or site_dir.name.startswith(("_", ".")) or site_dir.name in _SKIP_DIRS:
            continue
        for jf in sorted(site_dir.glob("*.json")):
            preset_id = f"{site_dir.name}/{jf.stem}"
            result.setdefault(preset_id, jf)
    return result


def list_presets() -> list[dict[str, Any]]:
    """Return metadata for all discovered presets (user > entry_points > builtin)."""
    merged: dict[str, Path] = {}
    merged.update(_scan_dir(BUILTIN_DIR))
    for pid, path in _scan_ep_presets().items():
        merged[pid] = path
    for pid, path in _scan_dir(USER_DIR).items():
        merged[pid] = path

    result = []
    for pid in sorted(merged):
        try:
            data = json.loads(merged[pid].read_text(encoding="utf-8"))
        except Exception:
            continue
        auth = data.get("auth") or {}
        ptype = (data.get("pagination") or {}).get("type", "none")
        result.append({
            "id": pid,
            "name": data.get("name", pid),
            "description": data.get("description", ""),
            "mode": data.get("mode", "fetch"),
            "vars": list((data.get("vars") or {}).keys()),
            "var_defs": data.get("vars") or {},
            "path": str(merged[pid]),
            "auth": auth.get("type", "cookie"),
            "auth_hint": auth.get("hint", ""),
            "paginated": ptype not in ("", "none", None),
        })
    return result


def load_preset(preset_id: str) -> dict[str, Any]:
    """Load a preset by ID (e.g. ``rakuten/rpp-search``).

    Raises ``FileNotFoundError`` if not found.
    """
    for source in (USER_DIR, None, BUILTIN_DIR):
        if source is None:
            ep = _scan_ep_presets()
            if preset_id in ep:
                return json.loads(ep[preset_id].read_text(encoding="utf-8"))
            continue
        path = source / preset_id.replace("/", str(Path("/"))).rstrip("/")
        json_path = path.with_suffix(".json")
        if json_path.is_file():
            return json.loads(json_path.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"Preset not found: {preset_id}")


_PRESET_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+$")


def _assert_safe_preset_id(preset_id: str, *, role: str) -> None:
    """Reject path traversal and other non-ID strings before path joins."""
    if not _PRESET_ID_RE.match(preset_id):
        raise ValueError(
            f"Invalid {role} preset ID '{preset_id}' — must be <site>/<action> "
            f"(alphanumeric, hyphens, underscores only)"
        )


def fork_preset(
    src_id: str,
    dst_id: str | None = None,
    *,
    force: bool = False,
) -> Path:
    """Copy a preset to the user directory for editing.

    *dst_id* defaults to *src_id* (same-name override of builtins).
    Returns the absolute path of the written file.
    Raises ``FileNotFoundError`` (source missing), ``ValueError`` (bad ID),
    or ``FileExistsError`` (target exists without *force*).
    """
    _assert_safe_preset_id(src_id, role="source")
    if dst_id is None:
        dst_id = src_id
    else:
        _assert_safe_preset_id(dst_id, role="destination")

    data = load_preset(src_id)
    site, name = dst_id.split("/", 1)
    dst_path = USER_DIR / site / f"{name}.json"

    if dst_path.exists() and not force:
        raise FileExistsError(
            f"Already exists: {dst_path}\n  Use --force to overwrite."
        )

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    dst_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return dst_path


def _scan_ep_presets() -> dict[str, Path]:
    """Discover presets from ``ziniao.sites`` entry-points group."""
    result: dict[str, Path] = {}
    try:
        from importlib.metadata import entry_points  # pylint: disable=import-outside-toplevel
        eps = entry_points()
        group = eps.get("ziniao.sites", []) if isinstance(eps, dict) else eps.select(group="ziniao.sites")
        for ep in group:
            try:
                plugin_cls = ep.load()
                pkg_dir = Path(plugin_cls.__module__.replace(".", "/")).parent
                if pkg_dir.is_dir():
                    result.update(_scan_dir(pkg_dir))
            except Exception:
                continue
    except Exception:
        pass
    return result


# ---------------------------------------------------------------------------
# Plugin loading
# ---------------------------------------------------------------------------

def get_plugin(site_name: str) -> SitePlugin | None:
    """Try to load a ``SitePlugin`` subclass for *site_name*.

    Checks user-local → entry_points → builtin ``__init__.py``.
    Returns ``None`` if no plugin is defined (JSON-only preset).
    """
    for base in (USER_DIR, BUILTIN_DIR):
        init_py = base / site_name / "__init__.py"
        if init_py.is_file():
            return _load_plugin_from_file(init_py, site_name)

    try:
        from importlib.metadata import entry_points  # pylint: disable=import-outside-toplevel
        eps = entry_points()
        group = eps.get("ziniao.sites", []) if isinstance(eps, dict) else eps.select(group="ziniao.sites")
        for ep in group:
            if ep.name == site_name:
                cls = ep.load()
                if isinstance(cls, type) and issubclass(cls, SitePlugin):
                    return cls()
    except Exception:
        pass
    return None


def _load_plugin_from_file(path: Path, site_name: str) -> SitePlugin | None:
    """Import a Python file and return the first ``SitePlugin`` subclass instance."""
    import importlib.util  # pylint: disable=import-outside-toplevel

    spec = importlib.util.spec_from_file_location(f"ziniao_site_{site_name}", path)
    if not spec or not spec.loader:
        return None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception:
        return None
    for attr in dir(mod):
        obj = getattr(mod, attr)
        if isinstance(obj, type) and issubclass(obj, SitePlugin) and obj is not SitePlugin:
            return obj()
    return None


# ---------------------------------------------------------------------------
# Variable rendering
# ---------------------------------------------------------------------------

def render_vars(template: dict, var_values: dict[str, str]) -> dict:
    """Replace ``{{var}}`` placeholders in *template* with *var_values*.

    - String values: simple replacement.
    - When ``"{{var}}"`` is the sole content of a JSON value and the var
      definition declares ``type: int/float/bool``, the value is coerced.
    """
    var_defs: dict = template.get("vars") or {}
    defaults = {k: v["default"] for k, v in var_defs.items() if "default" in v}
    merged = {**defaults, **var_values}

    for k, vdef in var_defs.items():
        if vdef.get("required") and k not in merged:
            raise ValueError(f"Required variable missing: {k}")

    result = json.loads(json.dumps(template))
    result.pop("vars", None)

    def _replace(obj: Any) -> Any:
        if isinstance(obj, str):
            match = _VAR_RE.fullmatch(obj)
            if match:
                var_name = match.group(1)
                if var_name in merged:
                    return _coerce(merged[var_name], var_defs.get(var_name, {}))
                return obj
            return _VAR_RE.sub(lambda m: str(merged.get(m.group(1), m.group(0))), obj)
        if isinstance(obj, dict):
            return {k: _replace(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_replace(v) for v in obj]
        return obj

    for key in ("url", "body", "headers", "script"):
        if key in result:
            result[key] = _replace(result[key])
    return result


def _coerce(value: Any, var_def: dict) -> Any:
    """Coerce a string value to the type declared in the var definition."""
    vtype = var_def.get("type", "str")
    if vtype == "int":
        try:
            return int(value)
        except (ValueError, TypeError):
            return value
    if vtype == "float":
        try:
            return float(value)
        except (ValueError, TypeError):
            return value
    if vtype == "bool":
        if isinstance(value, bool):
            return value
        return str(value).lower() in ("true", "1", "yes")
    return value


# ---------------------------------------------------------------------------
# Shared execution helpers
# ---------------------------------------------------------------------------

def prepare_request(
    *,
    preset: str = "",
    file: str = "",
    script: str = "",
    url: str = "",
    method: str = "GET",
    body: str = "",
    headers: dict | None = None,
    xsrf_cookie: str = "",
    var_values: dict[str, str] | None = None,
) -> tuple[dict, SitePlugin | None]:
    """Build a unified request spec from preset / file / CLI args.

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

    merged_vars = dict(var_values or {})
    if spec.get("vars"):
        spec = render_vars(spec, merged_vars)

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
    if xsrf_cookie:
        spec["xsrf_cookie"] = xsrf_cookie

    if isinstance(spec.get("body"), (dict, list)):
        spec["body"] = json.dumps(spec["body"], ensure_ascii=False)

    if plugin:
        spec = plugin.before_fetch(spec)

    return spec, plugin


def save_response_body(body_text: str, output_path: str) -> str:
    """Pretty-print JSON body if possible and write to *output_path*.

    Returns a human-readable confirmation message.
    """
    try:
        parsed = json.loads(body_text)
        body_text = json.dumps(parsed, ensure_ascii=False, indent=2)
    except (json.JSONDecodeError, TypeError):
        pass
    Path(output_path).write_text(body_text, encoding="utf-8")
    return f"Saved to {output_path} ({len(body_text)} bytes)"


# ---------------------------------------------------------------------------
# Pagination + multi-page fetch
# ---------------------------------------------------------------------------

def _get_nested(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if not part:
            continue
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _set_nested(obj: dict, path: str, value: Any) -> None:
    parts = [p for p in path.split(".") if p]
    if not parts:
        return
    cur: Any = obj
    for p in parts[:-1]:
        nxt = cur.get(p) if isinstance(cur, dict) else None
        if not isinstance(nxt, dict):
            cur[p] = {}
            nxt = cur[p]
        cur = nxt
    cur[parts[-1]] = value


def plugin_overrides_paginate(plugin: SitePlugin | None) -> bool:
    """True if *plugin* defines a custom ``paginate`` (not the base default)."""
    if plugin is None:
        return False
    return type(plugin).paginate is not SitePlugin.paginate


def _parse_body_dict(spec: dict) -> dict:
    b = spec.get("body")
    if isinstance(b, str):
        try:
            out = json.loads(b)
            return out if isinstance(out, dict) else {}
        except json.JSONDecodeError:
            return {}
    if isinstance(b, dict):
        return copy.deepcopy(b)
    return {}


def _spec_with_body_dict(spec: dict, body: dict) -> dict:
    s = copy.deepcopy(spec)
    s["body"] = json.dumps(body, ensure_ascii=False)
    return s


def paginate_all_generic(
    spec: dict,
    pagination: dict,
    fetch_sync: Callable[[dict], dict],
) -> tuple[dict, int, int]:
    """Merge all pages using JSON ``pagination`` config.

    Returns ``(merged_response_dict, http_status_first_page, pages_fetched)``.
    """
    ptype = pagination.get("type", "none")
    if ptype == "body_field":
        return _paginate_body_field(spec, pagination, fetch_sync)
    if ptype == "offset":
        return _paginate_offset(spec, pagination, fetch_sync)
    raise ValueError(f"Unsupported pagination.type: {ptype}")


def _paginate_body_field(
    spec: dict,
    pag: dict,
    fetch_sync: Callable[[dict], dict],
) -> tuple[dict, int, int]:
    page_field = pag.get("page_field", "page")
    total_field = pag.get("total_field", "")
    start = int(pag.get("start", 1))
    max_pages = int(pag.get("max_pages", 500))
    merge_items_field = pag.get("merge_items_field", "")

    body = _parse_body_dict(spec)
    body[page_field] = start
    first = fetch_sync(_spec_with_body_dict(spec, body))

    status = int(first.get("status", 200))
    if first.get("error") or status >= 400:
        try:
            merged = json.loads(first.get("body") or "{}")
        except (json.JSONDecodeError, TypeError):
            merged = {}
        return merged, status, 1

    text = first.get("body", "")
    try:
        first_data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {}, status, 1

    total = _get_nested(first_data, total_field) if total_field else 1
    try:
        total = int(total)
    except (TypeError, ValueError):
        total = 1
    total = max(1, min(total, max_pages))

    page_results = [first]
    for pnum in range(start + 1, total + 1):
        if pnum > max_pages:
            break
        b2 = _parse_body_dict(spec)
        b2[page_field] = pnum
        page_results.append(fetch_sync(_spec_with_body_dict(spec, b2)))

    merged = _merge_page_bodies(page_results, merge_items_field)
    return merged, status, len(page_results)


def _paginate_offset(
    spec: dict,
    pag: dict,
    fetch_sync: Callable[[dict], dict],
) -> tuple[dict, int, int]:
    offset_field = pag.get("offset_field", "offset")
    limit_field = pag.get("limit_field", "limit")
    limit = int(pag.get("limit", 50))
    start_offset = int(pag.get("start_offset", 0))
    total_field = pag.get("total_field", "")
    max_pages = int(pag.get("max_pages", 500))
    merge_items_field = pag.get("merge_items_field", "")

    body = _parse_body_dict(spec)
    body[offset_field] = start_offset
    body[limit_field] = limit
    first = fetch_sync(_spec_with_body_dict(spec, body))
    status = int(first.get("status", 200))
    if first.get("error") or status >= 400:
        try:
            return json.loads(first.get("body") or "{}"), status, 1
        except (json.JSONDecodeError, TypeError):
            return {}, status, 1

    try:
        first_data = json.loads(first.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}, status, 1

    total_count = _get_nested(first_data, total_field) if total_field else None
    try:
        total_count = int(total_count)
    except (TypeError, ValueError):
        total_count = limit

    num_pages = max(1, (total_count + limit - 1) // limit)
    num_pages = min(num_pages, max_pages)

    page_results = [first]
    for i in range(1, num_pages):
        off = start_offset + i * limit
        b2 = _parse_body_dict(spec)
        b2[offset_field] = off
        b2[limit_field] = limit
        page_results.append(fetch_sync(_spec_with_body_dict(spec, b2)))

    merged = _merge_page_bodies(page_results, merge_items_field)
    return merged, status, len(page_results)


def _merge_page_bodies(page_results: list[dict], merge_items_field: str) -> dict:
    if not page_results:
        return {}
    first_text = page_results[0].get("body", "") or "{}"
    try:
        first_data = json.loads(first_text)
    except (json.JSONDecodeError, TypeError):
        return {}

    if not merge_items_field or len(page_results) == 1:
        return first_data if isinstance(first_data, dict) else {}

    merged = json.loads(json.dumps(first_data))
    combined: list[Any] = []
    for pr in page_results:
        try:
            d = json.loads(pr.get("body") or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        chunk = _get_nested(d, merge_items_field)
        if isinstance(chunk, list):
            combined.extend(chunk)
    _set_nested(merged, merge_items_field, combined)
    return merged


async def _async_plugin_paginate_collect(
    plugin: SitePlugin,
    spec: dict,
    first_response: dict,
    fetch_sync: Callable[[dict], dict],
) -> dict:
    async def fetch_fn(s: dict) -> dict:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: fetch_sync(copy.deepcopy(s)))

    pages: list[dict] = []
    async for p in plugin.paginate(fetch_fn, copy.deepcopy(spec), copy.deepcopy(first_response)):
        pages.append(p)

    if not pages:
        return {"ok": False, "error": "plugin paginate yielded no pages"}
    if len(pages) == 1:
        return pages[0]
    parsed_pages = []
    for p in pages:
        b = p.get("body", "")
        try:
            parsed_pages.append(json.loads(b) if b else {})
        except (json.JSONDecodeError, TypeError):
            parsed_pages.append({"raw": b})
    status = int(pages[0].get("status", 200))
    return {
        "ok": True,
        "status": status,
        "body": json.dumps({"pages": parsed_pages}, ensure_ascii=False),
    }


def run_site_fetch(
    spec: dict,
    plugin: SitePlugin | None,
    fetch_sync: Callable[[dict], dict],
    *,
    fetch_all: bool = False,
) -> dict:
    """Run one page or all pages; ``plugin.after_fetch`` runs once at the end."""
    if not fetch_all:
        out = fetch_sync(copy.deepcopy(spec))
        if plugin and "body" in out:
            out = plugin.after_fetch(out, spec)
        return out

    if plugin_overrides_paginate(plugin):
        assert plugin is not None
        first = fetch_sync(copy.deepcopy(spec))
        out = asyncio.run(_async_plugin_paginate_collect(plugin, spec, first, fetch_sync))
        if plugin and "body" in out:
            out = plugin.after_fetch(out, spec)
        return out

    pagination = spec.get("pagination") or {}
    ptype = pagination.get("type", "none")
    if ptype in ("body_field", "offset"):
        try:
            merged_dict, status, pages_fetched = paginate_all_generic(spec, pagination, fetch_sync)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        out = {
            "ok": True,
            "status": status,
            "pages_fetched": pages_fetched,
            "body": json.dumps(merged_dict, ensure_ascii=False),
        }
        if plugin and "body" in out:
            out = plugin.after_fetch(out, spec)
        return out

    out = fetch_sync(copy.deepcopy(spec))
    if plugin and "body" in out:
        out = plugin.after_fetch(out, spec)
    return out
