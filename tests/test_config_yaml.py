"""``ziniao_mcp.config_yaml`` — merged project + global YAML (no argv)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ziniao_mcp.config_yaml import load_merged_project_and_global_yaml


def test_load_merged_project_and_global_yaml_merges_site_policy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    cfg_dir = cwd / "config"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text(
        yaml.safe_dump(
            {"site_policy": {"policies": {"example.com": {"default_mode": "passive"}}}},
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    zdir = home / ".ziniao"
    zdir.mkdir()
    (zdir / "config.yaml").write_text(
        yaml.safe_dump(
            {"site_policy": {"policies": {"other.test": {"default_mode": "passive"}}}},
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(cwd)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    merged = load_merged_project_and_global_yaml()
    pols = (merged.get("site_policy") or {}).get("policies") or {}
    assert "example.com" in pols
    assert "other.test" in pols
