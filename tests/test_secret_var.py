"""Unit tests for ``type: secret`` variable support.

Covers :func:`_resolve_secret` (keyring / env / interactive / explicit)
and the full-chain handling by :func:`render_vars` (secret values are
collected into ``_ziniao_secret_values`` for downstream masking).
"""

from __future__ import annotations

import pytest

from ziniao_mcp.sites import render_vars, _validate_ui_preset
from ziniao_mcp.sites import _resolve_secret  # noqa: PLC2701


# ---------------------------------------------------------------------------
# _resolve_secret — env source
# ---------------------------------------------------------------------------

def test_secret_env_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZINIAO_TEST_PWD", "hunter2")
    val = _resolve_secret(None, {"type": "secret", "source": "env:ZINIAO_TEST_PWD"})
    assert val == "hunter2"


def test_secret_env_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ZINIAO_MISSING_VAR", raising=False)
    with pytest.raises(ValueError, match="not set"):
        _resolve_secret(None, {"type": "secret", "source": "env:ZINIAO_MISSING_VAR"})


def test_secret_env_source_ignores_cli_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """When source is set, explicit value must be ignored (security)."""
    monkeypatch.setenv("ZINIAO_TEST_PWD", "from-env")
    val = _resolve_secret("from-cli", {"type": "secret", "source": "env:ZINIAO_TEST_PWD"})
    assert val == "from-env"


# ---------------------------------------------------------------------------
# _resolve_secret — explicit value fallback
# ---------------------------------------------------------------------------

def test_secret_explicit_value() -> None:
    val = _resolve_secret("literal-pw", {"type": "secret"})
    assert val == "literal-pw"


def test_secret_empty_noninteractive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    with pytest.raises(ValueError, match="secret value required"):
        _resolve_secret("", {"type": "secret"})


# ---------------------------------------------------------------------------
# _resolve_secret — keyring source
# ---------------------------------------------------------------------------

def test_secret_keyring_source(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkey-patch the keyring module to avoid system calls."""
    _kr = pytest.importorskip("keyring")
    monkeypatch.setattr(_kr, "get_password", lambda svc, key: "from-keyring" if (svc, key) == ("myapp", "admin") else None)
    val = _resolve_secret(None, {"type": "secret", "source": "keyring:myapp:admin"})
    assert val == "from-keyring"


def test_secret_keyring_malformed() -> None:
    with pytest.raises(ValueError, match="keyring:<service>:<key>"):
        _resolve_secret(None, {"type": "secret", "source": "keyring:incomplete"})


# ---------------------------------------------------------------------------
# render_vars — secret collection and masking pipeline
# ---------------------------------------------------------------------------

def test_render_vars_collects_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZINIAO_TEST_PWD", "s3cr3t")
    template = {
        "mode": "ui",
        "vars": {
            "user": {"type": "str", "required": True},
            "password": {"type": "secret", "source": "env:ZINIAO_TEST_PWD", "required": True},
        },
        "steps": [
            {"id": "login_u", "action": "fill", "selector": "#u", "value": "{{user}}"},
            {"id": "login_p", "action": "fill", "selector": "#p", "value": "{{password}}"},
        ],
    }
    rendered = render_vars(template, {"user": "alice"})
    assert "_ziniao_secret_values" in rendered
    assert rendered["_ziniao_secret_values"] == ["s3cr3t"]
    assert rendered["steps"][1]["value"] == "s3cr3t"


def test_render_vars_no_secret_no_marker() -> None:
    template = {
        "mode": "ui",
        "vars": {"q": {"type": "str", "required": True}},
        "steps": [{"action": "fill", "selector": "#q", "value": "{{q}}"}],
    }
    rendered = render_vars(template, {"q": "abc"})
    assert "_ziniao_secret_values" not in rendered


# ---------------------------------------------------------------------------
# _validate_ui_preset — schema + secret-placement checks
# ---------------------------------------------------------------------------

def test_validate_ui_preset_requires_steps() -> None:
    with pytest.raises(ValueError, match="steps"):
        _validate_ui_preset({"mode": "ui"})


def test_validate_ui_preset_action_whitelist() -> None:
    spec = {"mode": "ui", "steps": [{"action": "drop_database"}]}
    with pytest.raises(ValueError, match="whitelist"):
        _validate_ui_preset(spec)


def test_validate_ui_preset_extract_requires_as() -> None:
    spec = {"mode": "ui", "steps": [{"action": "extract", "selector": "a"}]}
    with pytest.raises(ValueError, match="'as'"):
        _validate_ui_preset(spec)


def test_validate_ui_preset_rejects_secret_in_url() -> None:
    spec = {
        "mode": "ui",
        "vars": {"pw": {"type": "secret"}},
        "steps": [{"action": "navigate", "url": "https://host/login?p={{pw}}"}],
    }
    with pytest.raises(ValueError, match="references secret var"):
        _validate_ui_preset(spec)


def test_validate_ui_preset_allows_secret_in_value() -> None:
    spec = {
        "mode": "ui",
        "vars": {"pw": {"type": "secret"}},
        "steps": [{"action": "fill", "selector": "#pw", "value": "{{pw}}"}],
    }
    _validate_ui_preset(spec)


def test_validate_ui_preset_duplicate_ids() -> None:
    spec = {
        "mode": "ui",
        "steps": [
            {"id": "a", "action": "click", "selector": "#x"},
            {"id": "a", "action": "click", "selector": "#y"},
        ],
    }
    with pytest.raises(ValueError, match="Duplicate"):
        _validate_ui_preset(spec)


def test_validate_ui_preset_skip_for_non_ui_mode() -> None:
    """fetch / js presets must not be validated with UI rules."""
    _validate_ui_preset({"mode": "fetch", "url": "https://x"})
    _validate_ui_preset({"mode": "js", "script": "fetch('/x')"})


def test_validate_ui_preset_rejects_secret_in_selector() -> None:
    """Regression: selectors were in the bypass list and leaked secrets to CDP."""
    spec = {
        "mode": "ui",
        "vars": {"pw": {"type": "secret"}},
        "steps": [{"action": "click", "selector": "button[data-pw={{pw}}]"}],
    }
    with pytest.raises(ValueError, match="references secret var"):
        _validate_ui_preset(spec)


def test_validate_ui_preset_rejects_secret_in_nested_dict() -> None:
    """Secret references must be caught recursively (fields_json etc. excepted)."""
    spec = {
        "mode": "ui",
        "vars": {"pw": {"type": "secret"}},
        "steps": [
            {
                "action": "eval",
                "script": "console.log('{{pw}}')",
            },
        ],
    }
    with pytest.raises(ValueError, match="references secret var"):
        _validate_ui_preset(spec)


def test_validate_ui_preset_rejects_secret_in_output_contract() -> None:
    """output_contract must never export a secret variable."""
    spec = {
        "mode": "ui",
        "vars": {"pw": {"type": "secret"}},
        "steps": [{"action": "fill", "selector": "#pw", "value": "{{pw}}"}],
        "output_contract": {"leaked": "$.vars.pw"},
    }
    with pytest.raises(ValueError, match="secrets must never appear in flow output"):
        _validate_ui_preset(spec)


def test_validate_ui_preset_allows_non_secret_vars_in_output() -> None:
    """Non-secret vars remain exportable."""
    spec = {
        "mode": "ui",
        "vars": {"user": {"type": "str"}},
        "steps": [{"action": "fill", "selector": "#u", "value": "{{user}}"}],
        "output_contract": {"who": "$.vars.user"},
    }
    _validate_ui_preset(spec)
