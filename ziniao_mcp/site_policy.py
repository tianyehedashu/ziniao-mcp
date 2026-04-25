"""High-risk site automation policy hints (passive / input-only vs nodriver+stealth).

Built-in defaults live in ``DEFAULT_SITE_POLICIES``. Optional YAML under top-level
``site_policy:`` merges / extends hosts and can set per-host ``policy_hint`` strings
(see ``docs/passive-input-automation.md``).
"""

from __future__ import annotations

import copy
import logging
from typing import Any

from urllib.parse import urlparse

_logger = logging.getLogger("ziniao-debug")

_SHOPEE_POLICY: dict[str, Any] = {
    "default_mode": "passive",
    "allow_runtime_attach": False,
    "allow_stealth": False,
    "allow_input_only": True,
}

# Shopee shares the same Datadome-style anti-bot front across regional TLDs;
# enumerate them explicitly so suffix matching also catches subdomains
# like ``mall.shopee.tw`` / ``seller.shopee.com``.
DEFAULT_SITE_POLICIES: dict[str, dict[str, Any]] = {
    host: dict(_SHOPEE_POLICY)
    for host in (
        "shopee.com",
        "shopee.com.my",
        "shopee.com.br",
        "shopee.tw",
        "shopee.sg",
        "shopee.co.id",
        "shopee.co.th",
        "shopee.ph",
        "shopee.vn",
        "shopee.mx",
        "shopee.cl",
        "shopee.co",
    )
}

_EFFECTIVE_POLICIES: dict[str, dict[str, Any]] | None = None


def reset_site_policies_cache() -> None:
    """Clear merged policies so the next lookup reloads YAML from disk.

    Intended for tests; daemons/CLI long-lived processes still need restart to
    pick up edited ``config.yaml``.
    """
    global _EFFECTIVE_POLICIES
    _EFFECTIVE_POLICIES = None


def _compute_effective_policies(
    builtins: dict[str, dict[str, Any]],
    section: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Shallow-merge YAML ``policies`` entries over *builtins* (per registrable host)."""
    section = section or {}
    policies_yaml = section.get("policies")
    if not isinstance(policies_yaml, dict):
        policies_yaml = {}
    out: dict[str, dict[str, Any]] = {h: dict(pol) for h, pol in builtins.items()}
    for raw_host, pol in policies_yaml.items():
        if not isinstance(raw_host, str) or not raw_host.strip():
            continue
        hn = normalize_host(raw_host)
        if not isinstance(pol, dict):
            _logger.warning("site_policy.policies[%r]: expected mapping, got %s", raw_host, type(pol))
            continue
        prev = dict(out.get(hn, {}))
        out[hn] = {**prev, **pol}
    return out


def configure_site_policies_from_merged_root(raw: dict[str, Any] | None = None) -> None:
    """Rebuild effective policies from a merged YAML root dict.

    If *raw* is ``None``, loads via :func:`ziniao_mcp.config_yaml.load_merged_raw_user_config_yaml`
    (same ``--config`` / project / ``~/.ziniao`` discovery as the daemon).
    """
    global _EFFECTIVE_POLICIES
    if raw is None:
        from ziniao_mcp.config_yaml import load_merged_raw_user_config_yaml  # pylint: disable=import-outside-toplevel

        raw = load_merged_raw_user_config_yaml()
    sp = raw.get("site_policy") if isinstance(raw, dict) else None
    if sp is not None and not isinstance(sp, dict):
        _logger.warning("site_policy: expected mapping at top level, got %s", type(sp))
        sp = {}
    _EFFECTIVE_POLICIES = _compute_effective_policies(DEFAULT_SITE_POLICIES, sp)


def _effective_policies() -> dict[str, dict[str, Any]]:
    global _EFFECTIVE_POLICIES
    if _EFFECTIVE_POLICIES is None:
        configure_site_policies_from_merged_root(None)
    assert _EFFECTIVE_POLICIES is not None
    return _EFFECTIVE_POLICIES


def normalize_host(host: str) -> str:
    h = (host or "").strip().lower()
    while h.endswith("."):
        h = h[:-1]
    return h


def host_from_url_or_host(value: str) -> str:
    """Host from ``https://a.b/c`` or bare ``shopee.com.my/path``."""
    s = (value or "").strip()
    if not s:
        return ""
    if "://" in s:
        parsed = urlparse(s)
        netloc = (parsed.netloc or "").lower()
        return netloc.split("@")[-1].split(":")[0]
    return normalize_host(s.split("/")[0].split("?")[0])


def get_site_policy(host_or_url: str) -> dict[str, Any] | None:
    """Return merged policy dict for host / URL, or None if unknown."""
    h = host_from_url_or_host(host_or_url)
    if not h:
        return None
    pols = _effective_policies()
    if h in pols:
        return dict(pols[h])
    for key, pol in pols.items():
        if h == key or h.endswith("." + key):
            return dict(pol)
    return None


def policy_hint_for_url(url: str) -> str | None:
    """Short user-facing hint for CLI JSON / text output."""
    pol = get_site_policy(url)
    if not pol:
        return None
    custom = pol.get("policy_hint")
    if isinstance(custom, str) and custom.strip():
        return custom.strip()
    mode = str(pol.get("default_mode") or "")
    if mode == "passive":
        host = host_from_url_or_host(url) or "this host"
        return (
            f"Site policy ({host}): default_mode=passive; avoid ``ziniao chrome connect`` "
            "(nodriver+stealth). Prefer ``launch-passive`` → ``passive-open`` → ``ziniao chrome input …``."
        )
    return None


def builtin_policies_snapshot() -> dict[str, dict[str, Any]]:
    """Deep copy of built-in defaults (tests / introspection)."""
    return copy.deepcopy(DEFAULT_SITE_POLICIES)
