"""Shared YAML helpers: load file, project↔global fall-through merge, merged root dict.

Used by :mod:`ziniao_mcp.server` (``_resolve_config``) and :mod:`ziniao_mcp.site_policy`
so CLI/daemon share the same discovery rules for ``--config`` / ``config/config.yaml`` /
``~/.ziniao/config.yaml`` without importing the MCP server stack from site_policy.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

_logger = logging.getLogger("ziniao-debug")


def _load_yaml_file(path: Path | str | None) -> dict[str, Any]:
    """Load a YAML config file into a dict, tolerating missing/empty/malformed input."""
    if not path:
        return {}
    p = Path(path)
    if not p.is_file():
        return {}
    import yaml  # pylint: disable=import-outside-toplevel

    try:
        with p.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError) as exc:
        _logger.warning("读取配置文件 %s 失败：%s", p, exc)
        return {}


def _merge_yaml_fallthrough(project: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    """Deep merge *project* over *base*.

    项目侧的 "falsy" 标量（None / 空字符串 / 0 / False）**不** 覆盖 base。
    """
    merged: dict[str, Any] = dict(base)
    for key, pv in project.items():
        bv = base.get(key)
        if isinstance(pv, dict) and isinstance(bv, dict):
            merged[key] = _merge_yaml_fallthrough(pv, bv)
        elif isinstance(pv, dict):
            merged[key] = pv
        elif pv in (None, "", 0, False):
            if key not in merged:
                merged[key] = pv
        else:
            merged[key] = pv
    return merged


def load_merged_project_and_global_yaml() -> dict[str, Any]:
    """Project ``config/config.yaml`` + ``~/.ziniao/config.yaml`` fall-through merge (no argv)."""
    project_raw: dict[str, Any] = {}
    project_candidates = [
        Path("config/config.yaml"),
        Path(__file__).resolve().parent.parent / "config" / "config.yaml",
    ]
    for p in project_candidates:
        if p.is_file():
            project_raw = _load_yaml_file(p)
            break
    global_raw = _load_yaml_file(Path.home() / ".ziniao" / "config.yaml")
    return _merge_yaml_fallthrough(project_raw, global_raw)


def load_merged_raw_user_config_yaml() -> dict[str, Any]:
    """Return merged raw YAML root (same file discovery as ``_resolve_config``).

    - If ``--config PATH`` is present on ``sys.argv``, load that file only.
    - Otherwise: :func:`load_merged_project_and_global_yaml`.

    Loads ``.env`` via ``dotenv_loader`` for consistency with the daemon.
    Does **not** call ``_print_package_version_and_exit`` (caller handles MCP/CLI exits).
    """
    from .dotenv_loader import load_dotenv  # pylint: disable=import-outside-toplevel

    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None)
    args, _ = parser.parse_known_args()
    if args.config:
        return _load_yaml_file(args.config)
    return load_merged_project_and_global_yaml()
