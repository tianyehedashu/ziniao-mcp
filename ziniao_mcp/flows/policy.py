"""Load ``~/.ziniao/policy.yaml`` and answer capability checks for RPA flows."""

from __future__ import annotations

import ipaddress
import os
import socket
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_POLICY: dict[str, Any] = {
    "external_call": {
        "http": {
            "enabled": True,
            "allow_private_network": False,
            "url_allowlist": [],
        },
        "mcp": {"enabled": False, "tool_allowlist": []},
    },
    "code_step": {
        "enabled": True,
        "language_allowlist": ["python"],
        "max_runtime_seconds": 5,
        "max_output_kb": 64,
    },
    "local_command": {"enabled": False},
    "file_write_outside_workspace": {"enabled": False},
}


def default_policy_path() -> Path:
    return Path.home() / ".ziniao" / "policy.yaml"


def load_policy(path: Path | None = None) -> dict[str, Any]:
    """Return merged policy dict (defaults + YAML overrides when file exists)."""
    base = yaml.safe_load(yaml.dump(_DEFAULT_POLICY)) or dict(_DEFAULT_POLICY)
    p = path or default_policy_path()
    if not p.is_file():
        return base
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return base
    if not isinstance(raw, dict):
        return base
    # shallow merge top-level keys only (KISS)
    merged = dict(base)
    for k, v in raw.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = {**merged[k], **v}
        else:
            merged[k] = v
    return merged


def merge_policy(base: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    """Recursively merge a flow-local policy override into *base*."""
    if not isinstance(override, dict):
        return base
    merged = yaml.safe_load(yaml.dump(base)) or dict(base)

    def _merge(dst: dict[str, Any], src: dict[str, Any]) -> dict[str, Any]:
        for key, val in src.items():
            if isinstance(val, dict) and isinstance(dst.get(key), dict):
                dst[key] = _merge(dict(dst[key]), val)
            else:
                dst[key] = val
        return dst

    return _merge(merged, override)


def _host_private(host: str) -> bool:
    h = host.lower().strip("[]").rstrip(".")
    if not h:
        return True
    if h == "localhost" or h.endswith(".localhost"):
        return True

    def _blocked_ip(value: str) -> bool:
        try:
            ip = ipaddress.ip_address(value)
        except ValueError:
            return False
        return any(
            (
                ip.is_private,
                ip.is_loopback,
                ip.is_link_local,
                ip.is_unspecified,
                ip.is_reserved,
                ip.is_multicast,
            )
        )

    if _blocked_ip(h):
        return True
    try:
        infos = socket.getaddrinfo(h, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        # Fail closed: a later resolver answer could still point at private infra.
        return True
    return any(_blocked_ip(info[4][0]) for info in infos)


def allows_mcp_tool(policy: dict[str, Any], server: str, tool: str) -> bool:
    """Return True if *server*/*tool* may be invoked per ``external_call.mcp``."""
    mcp = (policy.get("external_call") or {}).get("mcp") or {}
    if not mcp.get("enabled", False):
        return False
    allow = list(mcp.get("tool_allowlist") or [])
    if not allow:
        return False
    if "*" in allow:
        return True
    key = f"{server}:{tool}"
    return key in allow or f"{server}:*" in allow


def allows_local_io_path(path: Path, policy: dict[str, Any]) -> bool:
    """Restrict file read/write to cwd / ``~/.ziniao`` / temp unless policy allows arbitrary paths."""
    try:
        resolved = path.expanduser().resolve()
    except OSError:
        return False
    if (policy.get("file_write_outside_workspace") or {}).get("enabled", False):
        return True
    cwd = Path.cwd().resolve()
    ziniao_home = (Path.home() / ".ziniao").resolve()
    bases = [cwd, ziniao_home]
    raw_tmp = os.environ.get("TEMP") or os.environ.get("TMP") or os.environ.get("TMPDIR")
    if raw_tmp:
        try:
            bases.append(Path(raw_tmp).resolve())
        except OSError:
            pass
    rs = str(resolved)
    for base in bases:
        bs = str(base)
        if rs == bs or rs.startswith(bs + os.sep):
            return True
    return False


def allows_http_url(policy: dict[str, Any], url: str, *, allow_private_override: bool = False) -> bool:
    """Return True if *url* may be called per policy (SSRF + allowlist)."""
    http = (policy.get("external_call") or {}).get("http") or {}
    if not http.get("enabled", True):
        return False
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.hostname or ""
    if not host:
        return False
    allow_private = allow_private_override or bool(http.get("allow_private_network"))
    if not allow_private and _host_private(host):
        return False
    patterns = http.get("url_allowlist") or []
    if not patterns:
        return True
    for pat in patterns:
        if pat == "*":
            return True
        # glob-like: very small KISS — suffix * only
        if isinstance(pat, str) and pat.endswith("*") and url.startswith(pat[:-1]):
            return True
        if isinstance(pat, str) and pat == url:
            return True
    return False
