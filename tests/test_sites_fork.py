"""Unit tests for fork_preset.

Uses the fake repo from the ``rakuten_repo`` fixture in ``conftest.py``
so that ``rakuten/rpp-search`` is discoverable.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import ziniao_mcp.sites as sites_mod
from ziniao_mcp.sites import fork_preset


@pytest.fixture(autouse=True)
def _setup(rakuten_repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sites_mod, "USER_DIR", tmp_path)


def test_fork_same_id(tmp_path: Path) -> None:
    path = fork_preset("rakuten/rpp-search")
    assert path == tmp_path / "rakuten" / "rpp-search.json"
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["url"] == "https://ad.rms.rakuten.co.jp/rpp/api/reports/search"


def test_fork_custom_dst(tmp_path: Path) -> None:
    path = fork_preset("rakuten/rpp-search", "acme/rpp-custom")
    assert path == tmp_path / "acme" / "rpp-custom.json"
    assert path.exists()


def test_fork_exists_no_force(tmp_path: Path) -> None:
    fork_preset("rakuten/rpp-search")
    with pytest.raises(FileExistsError):
        fork_preset("rakuten/rpp-search")


def test_fork_exists_with_force(tmp_path: Path) -> None:
    fork_preset("rakuten/rpp-search")
    path = fork_preset("rakuten/rpp-search", force=True)
    assert path.exists()


def test_fork_invalid_dst_id() -> None:
    with pytest.raises(ValueError, match="Invalid destination preset ID"):
        fork_preset("rakuten/rpp-search", "../escape")


def test_fork_invalid_src_id_path_traversal() -> None:
    with pytest.raises(ValueError, match="Invalid source preset ID"):
        fork_preset("rakuten/../../../etc/passwd", "acme/foo")


def test_fork_not_found() -> None:
    with pytest.raises(FileNotFoundError):
        fork_preset("nonexistent/preset")
