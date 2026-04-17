"""Site preset discovery, loading, and variable rendering.

Discovery order (same preset ID → first match wins):
1. User-local  ``~/.ziniao/sites/<site>/<preset>.json``
2. entry_points group ``ziniao.sites`` (pip-installed third-party)
3. Built-in    ``ziniao_mcp/sites/<site>/<preset>.json``

Optional JSON fields on presets:

- ``auth``: ``{ "type": "cookie"|"xsrf"|"token"|"none", "hint": "..." }``
- ``header_inject``: ``list[dict]`` — declarative header injection rules.
  Each entry: ``{ "header": str, "source": "cookie"|"localStorage"|"sessionStorage"|"eval",
  "key": str, "expression": str, "transform": str }``.
- ``pagination``: ``body_field`` / ``offset`` config for ``--all`` (see built-in examples).
"""

from __future__ import annotations

import asyncio
import base64
import copy
import json
import re
from pathlib import Path
from typing import Any, Callable

from ._base import SitePlugin  # noqa: F401 — re-export for convenience

BUILTIN_DIR = Path(__file__).parent
USER_DIR = Path.home() / ".ziniao" / "sites"


# ---------------------------------------------------------------------------
# Body byte decoding helpers
# ---------------------------------------------------------------------------

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


def _source_for_path(p: Path) -> str:
    if p.is_relative_to(USER_DIR):
        return "local"
    from . import repo as _repo_mod  # pylint: disable=import-outside-toplevel
    if p.is_relative_to(_repo_mod.REPOS_DIR):
        return "repo"
    if p.is_relative_to(BUILTIN_DIR):
        return "builtin"
    return "unknown"


def list_presets() -> list[dict[str, Any]]:
    """Return metadata for all discovered presets (user > repos > entry_points > builtin)."""
    from . import repo as _repo_mod  # pylint: disable=import-outside-toplevel

    merged: dict[str, Path] = {}
    merged.update(_scan_dir(BUILTIN_DIR))
    for pid, path in _scan_ep_presets().items():
        merged[pid] = path
    for pid, path in _repo_mod.scan_repos().items():
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
            "source": _source_for_path(merged[pid]),
            "auth": auth.get("type", "cookie"),
            "auth_hint": auth.get("hint", ""),
            "paginated": ptype not in ("", "none", None),
        })
    return result


def load_preset(preset_id: str) -> dict[str, Any]:
    """Load a preset by ID (e.g. ``rakuten/rpp-search``).

    Search order: user-local → repos → entry_points → builtin.
    Raises ``FileNotFoundError`` if not found.
    """
    path = USER_DIR / preset_id.replace("/", str(Path("/"))).rstrip("/")
    json_path = path.with_suffix(".json")
    if json_path.is_file():
        return json.loads(json_path.read_text(encoding="utf-8"))

    from . import repo as _repo_mod  # pylint: disable=import-outside-toplevel
    repo_preset_path = _repo_mod.scan_repos().get(preset_id)
    if isinstance(repo_preset_path, Path) and repo_preset_path.is_file():
        return json.loads(repo_preset_path.read_text(encoding="utf-8"))

    ep = _scan_ep_presets()
    if preset_id in ep:
        return json.loads(ep[preset_id].read_text(encoding="utf-8"))

    builtin_path = BUILTIN_DIR / preset_id.replace("/", str(Path("/"))).rstrip("/")
    builtin_json = builtin_path.with_suffix(".json")
    if builtin_json.is_file():
        return json.loads(builtin_json.read_text(encoding="utf-8"))
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

    Checks user-local file → repo dirs → builtin package ``ziniao_mcp.sites.<site>``
    → entry_points.  Builtin plugins use normal package import so relative imports
    work; file-only loading is used for user-local and repo plugins.
    Returns ``None`` if no plugin is defined (JSON-only preset).
    """
    user_init = USER_DIR / site_name / "__init__.py"
    if user_init.is_file():
        loaded = _load_plugin_from_file(user_init, site_name)
        if loaded is not None:
            return loaded

    from . import repo as _repo_mod  # pylint: disable=import-outside-toplevel
    if _repo_mod.REPOS_DIR.is_dir():
        for repo_dir in sorted(_repo_mod.REPOS_DIR.iterdir()):
            if not repo_dir.is_dir() or repo_dir.name.startswith((".", "_")):
                continue
            if repo_dir.name == "__pycache__":
                continue
            repo_init = repo_dir / site_name / "__init__.py"
            if repo_init.is_file():
                loaded = _load_plugin_from_file(repo_init, site_name)
                if loaded is not None:
                    return loaded

    if (BUILTIN_DIR / site_name / "__init__.py").is_file():
        import importlib  # pylint: disable=import-outside-toplevel

        try:
            mod = importlib.import_module(f"ziniao_mcp.sites.{site_name}")
        except ModuleNotFoundError:
            pass
        else:
            explicit = getattr(mod, "SITE_PLUGIN", None)
            if explicit is not None:
                if not (isinstance(explicit, type) and issubclass(explicit, SitePlugin) and explicit is not SitePlugin):
                    raise TypeError(f"{mod.__name__}.SITE_PLUGIN must be a SitePlugin subclass")
                return explicit()
            subs: list[type] = []
            for attr in dir(mod):
                obj = getattr(mod, attr)
                if isinstance(obj, type) and issubclass(obj, SitePlugin) and obj is not SitePlugin:
                    subs.append(obj)
            if len(subs) == 1:
                return subs[0]()
            if len(subs) > 1:
                names = ", ".join(s.__name__ for s in subs)
                raise ValueError(
                    f"Sites package {site_name!r} defines multiple SitePlugin classes ({names}); set SITE_PLUGIN"
                )

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
      definition declares ``type: int/float/bool/file/file_list/secret``,
      the value is coerced via :func:`_coerce`.
    - Resolved ``secret`` values are collected into
      ``result['_ziniao_secret_values']`` so the UI flow executor can mask
      them in logs / failure artefacts.  ``steps`` (used by ``mode: ui``)
      is traversed alongside the fetch/js keys.
    """
    var_defs: dict = template.get("vars") or {}
    defaults = {k: v["default"] for k, v in var_defs.items() if "default" in v}
    merged = {**defaults, **var_values}

    for k, vdef in var_defs.items():
        if vdef.get("required") and k not in merged:
            if vdef.get("type") == "secret" and vdef.get("source"):
                continue
            raise ValueError(f"Required variable missing: {k}")

    result = json.loads(json.dumps(template))
    result.pop("vars", None)

    resolved_cache: dict[str, Any] = {}
    secret_values: list[str] = []

    def _resolve(var_name: str) -> Any:
        if var_name in resolved_cache:
            return resolved_cache[var_name]
        vdef = dict(var_defs.get(var_name) or {})
        vdef.setdefault("_name", var_name)
        coerced = _coerce(merged.get(var_name, ""), vdef)
        resolved_cache[var_name] = coerced
        if vdef.get("type") == "secret" and isinstance(coerced, str) and coerced:
            secret_values.append(coerced)
        return coerced

    def _replace(obj: Any) -> Any:
        if isinstance(obj, str):
            match = _VAR_RE.fullmatch(obj)
            if match:
                var_name = match.group(1)
                if var_name in merged or var_name in var_defs:
                    return _resolve(var_name)
                return obj
            def _sub(m: Any) -> str:
                name = m.group(1)
                if name in merged or name in var_defs:
                    val = _resolve(name)
                    return str(val) if not isinstance(val, str) else val
                return m.group(0)
            return _VAR_RE.sub(_sub, obj)
        if isinstance(obj, dict):
            return {k: _replace(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_replace(v) for v in obj]
        return obj

    for key in ("url", "body", "headers", "script", "steps", "navigate_url"):
        if key in result:
            result[key] = _replace(result[key])

    if secret_values:
        result["_ziniao_secret_values"] = secret_values
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
    if vtype == "file":
        return _read_file_as_base64(str(value), var_def)
    if vtype == "file_list":
        return _read_file_list_as_refs(value, var_def)
    if vtype == "secret":
        return _resolve_secret(value, var_def)
    return value


# ---------------------------------------------------------------------------
# Secret variable resolution
# ---------------------------------------------------------------------------

def _resolve_secret(value: Any, var_def: dict) -> str:
    """Resolve a ``type: secret`` variable.

    Source precedence (in order):

    1. ``var_def["source"]``: ``keyring:<service>:<key>`` → keyring; ``env:<VAR>``
       → environment variable.  When set, a CLI-provided value is **ignored**
       (principle of least surprise — users shouldn't leak secrets via history).
    2. Explicit *value* passed through CLI / programmatic (``-V key=...``).
    3. Interactive ``getpass`` prompt when stdin is a TTY.

    Raises ``ValueError`` when no source yields a value.  Caller is expected
    to register the resolved string in ``spec['_ziniao_secret_values']`` so
    it can be masked from logs / snapshots.
    """
    source = str(var_def.get("source") or "").strip()
    if source.startswith("keyring:"):
        rest = source.split(":", 1)[1]
        parts = rest.split(":", 1)
        if len(parts) != 2 or not all(parts):
            raise ValueError(
                f"secret 'source' must be 'keyring:<service>:<key>', got: {source!r}"
            )
        service, key = parts
        try:
            import keyring  # pylint: disable=import-outside-toplevel
        except ImportError as exc:
            raise ImportError(
                "`keyring` package is required for 'keyring:' secret source; "
                "install with `pip install keyring`."
            ) from exc
        val = keyring.get_password(service, key)
        if val is None:
            raise ValueError(
                f"No secret found in keyring for service={service!r} key={key!r}."
            )
        return val

    if source.startswith("env:"):
        env_key = source[4:].strip()
        if not env_key:
            raise ValueError(f"secret 'source' env key empty: {source!r}")
        import os  # pylint: disable=import-outside-toplevel
        val = os.environ.get(env_key)
        if val is None:
            raise ValueError(f"Environment variable {env_key!r} not set.")
        return val

    if value is not None and str(value).strip():
        return str(value)

    import sys  # pylint: disable=import-outside-toplevel
    if sys.stdin.isatty():
        import getpass  # pylint: disable=import-outside-toplevel
        label = var_def.get("prompt") or var_def.get("_name") or "secret"
        return getpass.getpass(f"Enter {label}: ")

    raise ValueError(
        "secret value required — configure 'source' (keyring/env) or pass "
        "-V key=value (not recommended on shared machines)."
    )


_FILE_REF_PREFIX = "@@ZFILE@@"
_URL_REF_PREFIX = "@@ZURL@@"
_FILE_MAX_BYTES = 50 * 1024 * 1024  # 50 MB safety limit


def _read_file_as_base64(value: str, var_def: dict) -> str:
    """Resolve a file-type variable.

    Both **local files** and **URLs** are deferred: a lightweight
    ``@@ZFILE@@<path>`` / ``@@ZURL@@<url>`` token is returned so the
    CLI → daemon TCP message stays small.  :func:`resolve_file_refs`
    (called on the daemon side) expands these tokens into real base64.

    Raw base64 strings pass through unchanged.
    """
    value = value.strip()
    if not value:
        return ""

    if value.startswith(("http://", "https://")):
        return _URL_REF_PREFIX + value

    p = Path(value)
    if p.is_file():
        return _FILE_REF_PREFIX + str(p.resolve())

    if "/" in value or "\\" in value or value.startswith("."):
        raise FileNotFoundError(
            f"File variable points to non-existent path: {value}"
        )

    return value.replace("\n", "").replace("\r", "")


def _read_file_list_as_refs(value: Any, var_def: dict) -> list[str]:
    """Resolve a ``file_list`` variable to a list of file/URL reference tokens.

    Accepted inputs:

    - Python ``list`` of strings (programmatic callers).
    - Comma-separated string: ``"a.png,b.png,https://host/c.webp"``.
    - Single path/URL/base64 string (returned as a 1-element list).

    Empty / whitespace-only entries are skipped.  Each entry is resolved via
    :func:`_read_file_as_base64` so local paths, URLs and raw base64 are all
    accepted; the final list is safe to JSON-serialize and walked later by
    :func:`resolve_file_refs` on the daemon side.
    """
    if value is None:
        return []
    if isinstance(value, list):
        items: list[str] = [str(v) for v in value]
    else:
        text = str(value).strip()
        if not text:
            return []
        items = [part.strip() for part in text.split(",")]
    out: list[str] = []
    for item in items:
        if not item:
            continue
        out.append(_read_file_as_base64(item, var_def))
    return out


def _download_url_as_base64(url: str) -> str:
    """Download *url* and return base64-encoded content."""
    import urllib.request  # pylint: disable=import-outside-toplevel

    req = urllib.request.Request(url, headers={"User-Agent": "ziniao/site-preset"})
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
        raw_bytes = resp.read()
    if len(raw_bytes) > _FILE_MAX_BYTES:
        raise ValueError(
            f"Downloaded file too large ({len(raw_bytes)} bytes, "
            f"limit {_FILE_MAX_BYTES}): {url}"
        )
    return base64.b64encode(raw_bytes).decode("ascii")


def resolve_file_refs(obj: Any) -> Any:
    """Walk *obj* and expand ``@@ZFILE@@`` / ``@@ZURL@@`` tokens to base64.

    Called on the **daemon side** (inside ``dispatch``) where direct
    filesystem access is available and there is no TCP size constraint.
    """
    if isinstance(obj, str):
        if obj.startswith(_FILE_REF_PREFIX):
            fpath = Path(obj[len(_FILE_REF_PREFIX):])
            if not fpath.is_file():
                raise FileNotFoundError(f"File not found: {fpath}")
            size = fpath.stat().st_size
            if size > _FILE_MAX_BYTES:
                raise ValueError(
                    f"File too large ({size} bytes, "
                    f"limit {_FILE_MAX_BYTES}): {fpath}"
                )
            return base64.b64encode(fpath.read_bytes()).decode("ascii")
        if obj.startswith(_URL_REF_PREFIX):
            return _download_url_as_base64(obj[len(_URL_REF_PREFIX):])
        return obj
    if isinstance(obj, dict):
        return {k: resolve_file_refs(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [resolve_file_refs(v) for v in obj]
    return obj


# ---------------------------------------------------------------------------
# Shared execution helpers
# ---------------------------------------------------------------------------

_VALID_INJECT_SOURCES = frozenset({"cookie", "localStorage", "sessionStorage", "eval"})


# ---------------------------------------------------------------------------
# UI flow preset validation
# ---------------------------------------------------------------------------

UI_ACTION_WHITELIST = frozenset({
    "navigate", "wait", "click", "fill", "type_text", "insert_text",
    "press_key", "hover", "dblclick", "upload", "screenshot", "snapshot",
    "eval", "extract", "fetch",
})


# Fields where a `{{secret}}` placeholder is legitimate (posted as body /
# typed into a password input / sent as a header value).  Any *other* field
# -- including selectors, URLs, scripts, extract `attr` -- must NOT carry
# secret values, because:
#   * selectors are logged/echoed by CDP and may end up in daemon logs;
#   * URLs appear in `navigate` history, browser address bar, and network
#     panels;
#   * `eval` scripts get snapshotted on error.
_SECRET_ALLOWED_STEP_FIELDS = frozenset({"value", "text", "headers", "body", "fields_json"})


def _walk_strings(obj: Any):
    """Yield every string leaf in *obj* (recurses into dict/list)."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_strings(v)


def _validate_ui_preset(spec: dict) -> None:
    """Validate a ``mode: ui`` preset *before* rendering.

    Enforces:

    - ``steps`` present, non-empty, list of dicts.
    - Each step has an ``action`` in :data:`UI_ACTION_WHITELIST`.
    - ``action: extract`` requires ``as`` (where to store the result).
    - ``secret`` vars may only appear in the whitelist
      :data:`_SECRET_ALLOWED_STEP_FIELDS`.  Any other step field
      (``selector``, ``url``, ``script``, ``attr``, …) must NOT carry
      ``{{secret}}`` tokens, even nested inside dict/list values.
    - ``output_contract`` must not export ``$.vars.<secret>`` — flow output
      is user-facing and often logged / stored.

    Raises :class:`ValueError` on the first violation.
    """
    if spec.get("mode") != "ui":
        return

    steps = spec.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("mode: ui preset requires non-empty 'steps' list.")

    secret_names = {
        k for k, v in (spec.get("vars") or {}).items()
        if isinstance(v, dict) and v.get("type") == "secret"
    }

    def _contains_secret_token(node: Any) -> str | None:
        for leaf in _walk_strings(node):
            for sname in secret_names:
                if "{{" + sname + "}}" in leaf:
                    return sname
        return None

    seen_ids: set[str] = set()
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ValueError(f"steps[{idx}] must be an object, got {type(step).__name__}.")
        action = step.get("action")
        if action not in UI_ACTION_WHITELIST:
            raise ValueError(
                f"steps[{idx}] action={action!r} not in whitelist "
                f"{sorted(UI_ACTION_WHITELIST)}."
            )
        sid = step.get("id")
        if sid:
            if sid in seen_ids:
                raise ValueError(f"Duplicate step id: {sid!r}.")
            seen_ids.add(sid)
        if action == "extract" and not step.get("as"):
            raise ValueError(f"steps[{idx}] action=extract requires 'as' (target key).")

        if secret_names:
            for key, val in step.items():
                if key in _SECRET_ALLOWED_STEP_FIELDS:
                    continue
                leaked = _contains_secret_token(val)
                if leaked is not None:
                    raise ValueError(
                        f"steps[{idx}].{key} references secret var {leaked!r}; "
                        f"secrets may only appear in {sorted(_SECRET_ALLOWED_STEP_FIELDS)}."
                    )

    contract = spec.get("output_contract") or {}
    if isinstance(contract, dict) and secret_names:
        for out_key, expr in contract.items():
            if not isinstance(expr, str) or not expr.startswith("$.vars."):
                continue
            var_name = expr[len("$.vars."):].split(".", 1)[0]
            if var_name in secret_names:
                raise ValueError(
                    f"output_contract[{out_key!r}] exports secret var "
                    f"{var_name!r}; secrets must never appear in flow output."
                )


def _normalize_header_inject(spec: dict) -> None:
    """Validate and clean the ``header_inject`` list in *spec*.

    Each entry must have ``header`` (str) and ``source`` (one of cookie /
    localStorage / sessionStorage / eval).  Invalid or incomplete entries are
    silently dropped.  If the resulting list is empty the key is removed.

    Invoked from ``dispatch._page_fetch`` (single choke point for CLI + MCP);
    ``prepare_request`` does not call this.
    """
    raw = spec.get("header_inject")
    if not isinstance(raw, list):
        spec.pop("header_inject", None)
        return
    cleaned: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        header = str(item.get("header") or "").strip()
        source = str(item.get("source") or "").strip()
        if not header or source not in _VALID_INJECT_SOURCES:
            continue
        entry: dict = {"header": header, "source": source}
        if source == "eval":
            expr = str(item.get("expression") or "").strip()
            if not expr:
                continue
            entry["expression"] = expr
        else:
            key = str(item.get("key") or "").strip()
            if not key:
                continue
            entry["key"] = key
        transform = str(item.get("transform") or "").strip()
        if transform:
            entry["transform"] = transform
        cleaned.append(entry)
    if cleaned:
        spec["header_inject"] = cleaned
    else:
        spec.pop("header_inject", None)


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
        merged_for_plugin = {**defaults, **merged_input}
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

    # Fallback: body_text only (pagination-merged results, legacy callers)
    try:
        parsed = json.loads(body_text)
        body_text = json.dumps(parsed, ensure_ascii=False, indent=2)
    except (json.JSONDecodeError, TypeError):
        pass
    dest.write_text(body_text, encoding=output_encoding or "utf-8")
    return f"Saved to {output_path} ({len(body_text)} chars)"


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


def _spec_for_page_fetch(spec: dict) -> dict:
    """Deep-copy *spec* for ``page_fetch`` / daemon; drop CLI-only ``_ziniao_*`` keys."""
    out = copy.deepcopy(spec)
    for k in list(out.keys()):
        if k.startswith("_ziniao_"):
            out.pop(k, None)
    return out


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
    first = fetch_sync(_spec_for_page_fetch(_spec_with_body_dict(spec, body)))

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
        page_results.append(fetch_sync(_spec_for_page_fetch(_spec_with_body_dict(spec, b2))))

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
    first = fetch_sync(_spec_for_page_fetch(_spec_with_body_dict(spec, body)))
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
        page_results.append(fetch_sync(_spec_for_page_fetch(_spec_with_body_dict(spec, b2))))

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
        return await loop.run_in_executor(None, lambda: fetch_sync(_spec_for_page_fetch(s)))

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
        out = fetch_sync(_spec_for_page_fetch(spec))
        if plugin and "body" in out:
            out = plugin.after_fetch(out, spec)
        return out

    if plugin_overrides_paginate(plugin):
        assert plugin is not None
        first = fetch_sync(_spec_for_page_fetch(spec))
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

    out = fetch_sync(_spec_for_page_fetch(spec))
    if plugin and "body" in out:
        out = plugin.after_fetch(out, spec)
    return out
