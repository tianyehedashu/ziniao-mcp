"""Generic site plugin discovery: non-Python-identifier site dirs under repos."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ziniao_mcp.sites import list_presets, load_preset
from ziniao_mcp.sites import repo as repo_mod
from ziniao_mcp.sites.plugin_loader import get_plugin


@pytest.fixture()
def fake_repo_sites(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """One repo with site ``123test`` (invalid Python identifier)."""
    repos_root = tmp_path / "repos"
    site_dir = repos_root / "myrepo" / "123test"
    site_dir.mkdir(parents=True)
    (site_dir / "ping.json").write_text(
        json.dumps(
            {
                "name": "Test ping",
                "description": "fixture",
                "mode": "js",
                "script": "",
                "_ziniao_fixture_route": "ping",
                "vars": {},
                "body": {},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (site_dir / "__init__.py").write_text(
        '''"""Fixture site plugin."""
from __future__ import annotations
from typing import Any
from ziniao_mcp.sites._base import SitePlugin


class Fixture123TestPlugin(SitePlugin):
    site_id = "123test"

    def before_fetch(self, request: dict[str, Any], *, tab: Any = None, store: Any = None) -> dict[str, Any]:
        if request.get("_ziniao_fixture_route") == "ping":
            request["mode"] = "js"
            request["script"] = "(async () => JSON.stringify({ ok: true, fixture: true }))()"
            request.pop("_ziniao_fixture_route", None)
        return request


SITE_PLUGIN = Fixture123TestPlugin
''',
        encoding="utf-8",
    )
    monkeypatch.setattr(repo_mod, "REPOS_DIR", repos_root)
    monkeypatch.setattr(repo_mod, "ensure_official_repo", lambda: None)


def test_get_plugin_nonidentifier_site_from_repo(fake_repo_sites: None) -> None:
    assert not str("123test").isidentifier()
    plugin = get_plugin("123test")
    assert plugin is not None
    assert getattr(plugin, "site_id", "") == "123test"


def test_list_presets_marks_repo_source(fake_repo_sites: None) -> None:
    rows = [p for p in list_presets() if p["id"] == "123test/ping"]
    assert len(rows) == 1
    assert rows[0]["source"] == "repo"


def test_load_preset_prefers_repo_over_builtin(fake_repo_sites: None) -> None:
    data = load_preset("123test/ping")
    assert data.get("_ziniao_fixture_route") == "ping"


def test_before_fetch_strips_internal_route(fake_repo_sites: None) -> None:
    plugin = get_plugin("123test")
    assert plugin is not None
    spec = load_preset("123test/ping")
    out = plugin.before_fetch(spec)
    assert out.get("_ziniao_fixture_route") is None
    assert "fixture" in out.get("script", "")
