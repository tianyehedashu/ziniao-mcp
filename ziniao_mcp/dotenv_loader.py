"""Lightweight .env file loader — no external dependencies.

Loads environment variables from ``~/.ziniao/.env`` (global) and ``$CWD/.env``
(project-level).  Only sets keys that are **not already present** in
``os.environ``, so explicit env vars always win.
"""

from __future__ import annotations

import os
from pathlib import Path

_STATE_DIR = Path.home() / ".ziniao"
_LOADED: bool = False


def _parse_env_file(path: Path) -> dict[str, str]:
    """Parse a simple KEY=VALUE file, ignoring comments and blank lines."""
    result: dict[str, str] = {}
    if not path.is_file():
        return result
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            if key:
                result[key] = value
    except OSError:
        pass
    return result


def load_dotenv(*, extra_paths: list[Path | str] | None = None) -> dict[str, str]:
    """Load .env files into ``os.environ`` (only missing keys).

    Load order (later files override earlier for the *same key*,
    but nothing overrides a key already in ``os.environ``):

    1. ``~/.ziniao/.env``  (global)
    2. ``$CWD/.env``       (project)
    3. Any *extra_paths*

    Returns the merged dict of all parsed key-value pairs (before filtering).
    """
    global _LOADED  # noqa: PLW0603
    if _LOADED:
        return {}
    _LOADED = True

    sources: list[Path] = [
        _STATE_DIR / ".env",
        Path.cwd() / ".env",
    ]
    if extra_paths:
        sources.extend(Path(p) for p in extra_paths)

    merged: dict[str, str] = {}
    for src in sources:
        merged.update(_parse_env_file(src))

    applied: dict[str, str] = {}
    for key, value in merged.items():
        if key not in os.environ:
            os.environ[key] = value
            applied[key] = value

    return applied
