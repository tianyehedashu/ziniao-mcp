"""Unit tests for site repo management (add/update/remove/repos)."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

import ziniao_mcp.sites.repo as repo_mod
from ziniao_mcp.sites.repo import (
    add_repo,
    get_repo,
    list_repos,
    remove_repo,
    scan_repos,
    update_repo,
)


@pytest.fixture(autouse=True)
def _patch_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(repo_mod, "REPOS_DIR", tmp_path / "repos")
    monkeypatch.setattr(repo_mod, "REPOS_JSON", tmp_path / "repos" / "repos.json")
    monkeypatch.setattr(repo_mod, "ensure_official_repo", lambda: None)


def _write_repo_json(name: str, url: str, branch: str = "main") -> None:
    repos_dir = repo_mod.REPOS_DIR
    repos_dir.mkdir(parents=True, exist_ok=True)
    state = {"repos": [{"name": name, "url": url, "branch": branch, "added_at": "2026-01-01T00:00:00"}]}
    repo_mod.REPOS_JSON.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _make_repo_dir(name: str, sites: dict[str, list[str]] | None = None) -> Path:
    d = repo_mod.REPOS_DIR / name
    d.mkdir(parents=True, exist_ok=True)
    if sites:
        for site_name, presets in sites.items():
            site_dir = d / site_name
            site_dir.mkdir(exist_ok=True)
            for preset in presets:
                (site_dir / f"{preset}.json").write_text(
                    json.dumps({"name": f"{site_name}/{preset}", "url": "https://example.com"}),
                    encoding="utf-8",
                )
    return d


def _make_zip_bytes(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for path, content in files.items():
            zf.writestr(path, content)
    return buf.getvalue()


class TestListRepos:
    def test_empty(self):
        assert list_repos() == []

    def test_with_entries(self):
        _write_repo_json("test-repo", "https://example.com/test.git")
        repos = list_repos()
        assert len(repos) == 1
        assert repos[0]["name"] == "test-repo"
        assert repos[0]["url"] == "https://example.com/test.git"


class TestGetRepo:
    def test_not_found(self):
        assert get_repo("nonexistent") is None

    def test_found(self):
        _write_repo_json("my-repo", "https://example.com/my.git")
        r = get_repo("my-repo")
        assert r is not None
        assert r["name"] == "my-repo"


class TestAddRepo:
    def test_add_success(self):
        with patch("ziniao_mcp.sites.repo._download_and_extract"):
            entry = add_repo("https://example.com/test.git", name="test-repo")

        assert entry["name"] == "test-repo"
        assert entry["url"] == "https://example.com/test.git"
        repos = list_repos()
        assert len(repos) == 1

    def test_add_duplicate_fails(self):
        _write_repo_json("test-repo", "https://example.com/test.git")
        with pytest.raises(ValueError, match="already exists"):
            add_repo("https://example.com/test2.git", name="test-repo")

    def test_add_name_from_url(self):
        with patch("ziniao_mcp.sites.repo._download_and_extract"):
            entry = add_repo("https://github.com/myorg/my-sites.git")

        assert entry["name"] == "my-sites"

    def test_add_download_failure(self):
        with patch(
            "ziniao_mcp.sites.repo._download_and_extract",
            side_effect=RuntimeError("Download failed (HTTP 404)"),
        ):
            with pytest.raises(RuntimeError, match="Download failed"):
                add_repo("https://example.com/bad.git", name="bad")


class TestUrlToZip:
    def test_github(self):
        url = repo_mod._url_to_zip("https://github.com/org/repo.git", "main")
        assert url == "https://github.com/org/repo/archive/refs/heads/main.zip"

    def test_github_no_git_suffix(self):
        url = repo_mod._url_to_zip("https://github.com/org/repo", "dev")
        assert url == "https://github.com/org/repo/archive/refs/heads/dev.zip"

    def test_gitlab(self):
        url = repo_mod._url_to_zip("https://gitlab.com/org/repo.git", "main")
        assert "gitlab.com" in url
        assert ".zip" in url


class TestRemoveRepo:
    def test_remove_success(self, tmp_path: Path):
        _write_repo_json("test-repo", "https://example.com/test.git")
        _make_repo_dir("test-repo")

        result = remove_repo("test-repo")
        assert result["name"] == "test-repo"
        assert result["dir_removed"] is True
        assert get_repo("test-repo") is None
        assert not (tmp_path / "repos" / "test-repo").exists()

    def test_remove_not_found(self):
        with pytest.raises(ValueError, match="not found"):
            remove_repo("nonexistent")

    def test_remove_dir_missing(self):
        _write_repo_json("ghost-repo", "https://example.com/ghost.git")
        result = remove_repo("ghost-repo")
        assert result["dir_removed"] is False


class TestUpdateRepo:
    def test_update_no_repos(self):
        with pytest.raises(ValueError, match="No repos registered"):
            update_repo()

    def test_update_specific_not_found(self):
        with pytest.raises(ValueError, match="not found"):
            update_repo("nonexistent")

    def test_update_success(self):
        _write_repo_json("test-repo", "https://example.com/test.git")
        _make_repo_dir("test-repo")

        with patch("ziniao_mcp.sites.repo._download_and_extract"):
            results = update_repo("test-repo")

        assert len(results) == 1
        assert results[0]["status"] == "updated"

    def test_update_error(self):
        _write_repo_json("test-repo", "https://example.com/test.git")

        with patch(
            "ziniao_mcp.sites.repo._download_and_extract",
            side_effect=RuntimeError("Download failed (HTTP 500)"),
        ):
            results = update_repo("test-repo")

        assert results[0]["status"] == "error"
        assert "Download failed" in results[0]["error"]


class TestDownloadAndExtract:
    def test_extract_github_style_zip(self, tmp_path: Path):
        zip_bytes = _make_zip_bytes({
            "repo-main/": "",
            "repo-main/rakuten/": "",
            "repo-main/rakuten/search.json": json.dumps({"name": "search"}),
            "repo-main/amazon/": "",
            "repo-main/amazon/orders.json": json.dumps({"name": "orders"}),
        })

        target = tmp_path / "extracted"
        with patch("ziniao_mcp.sites.repo.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.content = zip_bytes
            repo_mod._download_and_extract("https://example.com/test.zip", target)

        assert (target / "rakuten" / "search.json").is_file()
        assert (target / "amazon" / "orders.json").is_file()
        data = json.loads((target / "rakuten" / "search.json").read_text())
        assert data["name"] == "search"


class TestScanRepos:
    def test_empty(self):
        assert scan_repos() == {}

    def test_scan_with_presets(self):
        _make_repo_dir("my-repo", {
            "rakuten": ["rpp-search", "rpp-exp-report"],
            "amazon": ["orders"],
        })

        found = scan_repos()
        assert "rakuten/rpp-search" in found
        assert "rakuten/rpp-exp-report" in found
        assert "amazon/orders" in found
        assert len(found) == 3

    def test_scan_skips_hidden_dirs(self, tmp_path: Path):
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir(parents=True, exist_ok=True)
        hidden = repos_dir / ".hidden"
        hidden.mkdir()
        (hidden / "site" / "action.json").mkdir(parents=True)
        found = scan_repos()
        assert len(found) == 0

    def test_scan_multiple_repos_first_wins(self):
        _make_repo_dir("repo-a", {"shared": ["action"]})
        _make_repo_dir("repo-b", {"shared": ["action"]})

        found = scan_repos()
        assert "shared/action" in found
        assert len(found) == 1
