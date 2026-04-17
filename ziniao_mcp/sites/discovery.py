"""Preset discovery, loading, and fork.

Discovery order (same preset ID → first match wins):

1. User-local  ``~/.ziniao/sites/<site>/<preset>.json``
2. Repos       ``~/.ziniao/repos/<repo>/<site>/<preset>.json``
3. entry_points group ``ziniao.sites`` (pip-installed third-party)
4. Built-in    ``ziniao_mcp/sites/<site>/<preset>.json``
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

BUILTIN_DIR = Path(__file__).parent
USER_DIR = Path.home() / ".ziniao" / "sites"

_SKIP_DIRS = {"__pycache__"}
_PRESET_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+$")


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
