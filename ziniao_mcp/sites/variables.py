"""Variable-type resolution for ``type: secret / file / file_list``.

``file`` / ``file_list`` vars first resolve to lightweight reference tokens
(``@@ZFILE@@<path>`` / ``@@ZURL@@<url>``) so the CLI → daemon TCP message
stays small; the daemon calls :func:`resolve_file_refs` to expand them into
real base64 right before the browser-side script runs.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

_FILE_REF_PREFIX = "@@ZFILE@@"
_URL_REF_PREFIX = "@@ZURL@@"
_TEXT_FILE_REF_PREFIX = "@file:"
_FILE_MAX_BYTES = 50 * 1024 * 1024  # 50 MB safety limit


def resolve_text_file_ref(value: Any) -> Any:
    """Expand a ``@file:<path>`` string into the file's UTF-8 text content.

    Non-string values and strings without the prefix pass through unchanged.
    Raises ``FileNotFoundError`` when the referenced path is missing, so
    callers fail fast rather than silently shipping a literal ``@file:…``
    string downstream.
    """
    if not isinstance(value, str) or not value.startswith(_TEXT_FILE_REF_PREFIX):
        return value
    fp = Path(value[len(_TEXT_FILE_REF_PREFIX):])
    if not fp.is_file():
        raise FileNotFoundError(f"@file: reference not found: {fp}")
    return fp.read_text(encoding="utf-8", errors="replace")


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
