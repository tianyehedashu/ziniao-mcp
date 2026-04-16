"""Site repo management: add, update, remove remote site preset repositories.

Repos live under ``~/.ziniao/repos/`` and are tracked in ``repos.json``.
Each repo is downloaded as a zip archive and extracted; the directory layout
follows ``<site>/<action>.json`` — identical to ``ziniao_mcp/sites/`` and
``~/.ziniao/sites/``.  No external tools (git) required.
"""

from __future__ import annotations

import io
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

REPOS_DIR = Path.home() / ".ziniao" / "repos"
REPOS_JSON = REPOS_DIR / "repos.json"
USER_SKILLS_DIR = Path.home() / ".ziniao" / "skills"

_OFFICIAL_REPO_URL = "https://github.com/tianyehedashu/site-hub.git"
_OFFICIAL_REPO_NAME = "site-hub"


def _builtin_skills_dir() -> Path | None:
    try:
        from ziniao_mcp import __file__ as _mod_file
        base = Path(_mod_file).resolve().parent
    except Exception:
        return None
    candidate = base.parent / "skills"
    return candidate if candidate.is_dir() else None


def _repos_state() -> dict[str, Any]:
    if REPOS_JSON.is_file():
        try:
            return json.loads(REPOS_JSON.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"repos": []}


def _save_state(state: dict[str, Any]) -> None:
    REPOS_DIR.mkdir(parents=True, exist_ok=True)
    REPOS_JSON.write_text(
        json.dumps(state, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _repo_dir(name: str) -> Path:
    return REPOS_DIR / name


def _url_to_zip(url: str, branch: str) -> str:
    if url.endswith(".git"):
        base = url[:-4]
    else:
        base = url.rstrip("/")

    if base.startswith("https://github.com/"):
        return f"{base}/archive/refs/heads/{branch}.zip"
    if base.startswith("https://gitlab.com/"):
        return f"{base}/-/archive/{branch}/{base.rsplit('/', 1)[-1]}.zip"
    return f"{base}/archive/{branch}.zip"


def _download_and_extract(zip_url: str, target: Path) -> None:
    resp = requests.get(zip_url, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(
            f"Download failed (HTTP {resp.status_code}): {zip_url}"
        )

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = zf.namelist()
        if not names:
            raise RuntimeError("Empty archive")

        prefix = names[0]
        if not prefix.endswith("/"):
            for n in names:
                if "/" in n:
                    prefix = n.split("/", 1)[0] + "/"
                    break
            else:
                prefix = ""

        if target.is_dir():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)

        for name in names:
            if name == prefix:
                continue
            if not name.startswith(prefix):
                continue
            rel = name[len(prefix):]
            if not rel:
                continue
            dest = target / rel
            if name.endswith("/"):
                dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(name) as src, open(dest, "wb") as dst:
                    dst.write(src.read())


def list_repos() -> list[dict[str, Any]]:
    return _repos_state().get("repos", [])


def get_repo(name: str) -> dict[str, Any] | None:
    for r in list_repos():
        if r["name"] == name:
            return r
    return None


def add_repo(
    url: str,
    *,
    name: str | None = None,
    branch: str = "main",
) -> dict[str, Any]:
    if not name:
        name = url.rstrip("/").rsplit("/", 1)[-1]
        if name.endswith(".git"):
            name = name[:-4]

    existing = get_repo(name)
    if existing:
        raise ValueError(
            f"Repo '{name}' already exists (URL: {existing['url']}). "
            f"Use 'site remove {name}' first, or specify --name."
        )

    REPOS_DIR.mkdir(parents=True, exist_ok=True)
    target = _repo_dir(name)
    zip_url = _url_to_zip(url, branch)
    _download_and_extract(zip_url, target)

    entry = {
        "name": name,
        "url": url,
        "branch": branch,
        "added_at": datetime.now(timezone.utc).isoformat(),
    }

    state = _repos_state()
    state["repos"].append(entry)
    _save_state(state)
    return entry


def update_repo(name: str | None = None) -> list[dict[str, Any]]:
    repos = list_repos()

    if name:
        repos = [r for r in repos if r["name"] == name]
        if not repos:
            raise ValueError(f"Repo '{name}' not found.")
    elif not repos:
        raise ValueError("No repos registered. Use 'site add <url>' first.")

    results: list[dict[str, Any]] = []

    for repo in repos:
        target = _repo_dir(repo["name"])
        zip_url = _url_to_zip(repo["url"], repo["branch"])
        try:
            _download_and_extract(zip_url, target)
            results.append({
                "name": repo["name"],
                "status": "updated",
            })
        except Exception as exc:
            results.append({
                "name": repo["name"],
                "status": "error",
                "error": str(exc),
            })

    return results


def remove_repo(name: str) -> dict[str, Any]:
    state = _repos_state()
    repos = state.get("repos", [])
    matching = [r for r in repos if r["name"] == name]
    if not matching:
        raise ValueError(f"Repo '{name}' not found.")

    state["repos"] = [r for r in repos if r["name"] != name]
    _save_state(state)

    target = _repo_dir(name)
    removed_dir = False
    if target.is_dir():
        shutil.rmtree(target)
        removed_dir = True

    return {"name": name, "dir_removed": removed_dir}


def ensure_official_repo() -> dict[str, Any] | None:
    if get_repo(_OFFICIAL_REPO_NAME):
        return None
    try:
        return add_repo(_OFFICIAL_REPO_URL, name=_OFFICIAL_REPO_NAME)
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            "Failed to auto-add official repo %s", _OFFICIAL_REPO_URL, exc_info=True
        )
        return None


def scan_repos() -> dict[str, Path]:
    ensure_official_repo()
    result: dict[str, Path] = {}
    if not REPOS_DIR.is_dir():
        return result
    for repo_dir in sorted(REPOS_DIR.iterdir()):
        if not repo_dir.is_dir() or repo_dir.name.startswith((".", "_")):
            continue
        if repo_dir.name == "__pycache__":
            continue
        for site_dir in sorted(repo_dir.iterdir()):
            if not site_dir.is_dir() or site_dir.name.startswith(("_", ".")):
                continue
            for jf in sorted(site_dir.glob("*.json")):
                preset_id = f"{site_dir.name}/{jf.stem}"
                result.setdefault(preset_id, jf)
    return result


def _scan_flat_skills(base: Path, result: dict[str, Path]) -> None:
    for skill_dir in sorted(base.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name.startswith(("_", ".")):
            continue
        skill_file = skill_dir / "SKILL.md"
        if skill_file.is_file():
            result.setdefault(skill_dir.name, skill_file)


def _scan_repo_skills(base: Path, result: dict[str, Path]) -> None:
    for repo_dir in sorted(base.iterdir()):
        if not repo_dir.is_dir() or repo_dir.name.startswith((".", "_")):
            continue
        if repo_dir.name == "__pycache__":
            continue
        repo_skills = repo_dir / "skills"
        if repo_skills.is_dir():
            _scan_flat_skills(repo_skills, result)
        for site_dir in sorted(repo_dir.iterdir()):
            if not site_dir.is_dir() or site_dir.name.startswith(("_", ".")):
                continue
            if site_dir.name == "skills":
                continue
            skills_dir = site_dir / "skills"
            if skills_dir.is_dir():
                for skill_dir in sorted(skills_dir.iterdir()):
                    if not skill_dir.is_dir() or skill_dir.name.startswith(("_", ".")):
                        continue
                    skill_file = skill_dir / "SKILL.md"
                    if skill_file.is_file():
                        result.setdefault(skill_dir.name, skill_file)
            else:
                skill_file = site_dir / "SKILL.md"
                if skill_file.is_file():
                    result.setdefault(site_dir.name, skill_file)


def _skill_source(skill_path: Path) -> str:
    builtin_dir = _builtin_skills_dir()
    if builtin_dir and skill_path.is_relative_to(builtin_dir):
        return "builtin"
    if skill_path.is_relative_to(USER_SKILLS_DIR):
        return "local"
    if skill_path.is_relative_to(REPOS_DIR):
        return "repo"
    return "unknown"


def scan_skills() -> dict[str, Path]:
    """Return ``{skill_name: SKILL.md_path}`` for all skill sources.

    Discovery order (first match wins — ``setdefault`` preserves earliest):
    1. Built-in     ``<package_root>/skills/<name>/SKILL.md``
    2. Repos        ``~/.ziniao/repos/<repo>/<site>/skills/<name>/SKILL.md``
    3. User-local   ``~/.ziniao/skills/<name>/SKILL.md``
    """
    ensure_official_repo()
    result: dict[str, Path] = {}
    builtin_dir = _builtin_skills_dir()
    if builtin_dir:
        _scan_flat_skills(builtin_dir, result)
    if REPOS_DIR.is_dir():
        _scan_repo_skills(REPOS_DIR, result)
    if USER_SKILLS_DIR.is_dir():
        _scan_flat_skills(USER_SKILLS_DIR, result)
    return result


def parse_skill_meta(skill_path: Path) -> dict[str, str]:
    """Parse YAML frontmatter from a SKILL.md file.

    Returns a dict with at least ``name`` and ``description``.
    """
    import re as _re

    text = skill_path.read_text(encoding="utf-8-sig")
    m = _re.match(r"^---\s*\n(.*?)\n---", text, _re.DOTALL)
    if not m:
        return {"name": skill_path.parent.name, "description": "", "path": str(skill_path)}

    meta: dict[str, str] = {"path": str(skill_path)}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    if "name" not in meta:
        meta["name"] = skill_path.parent.name
    meta["source"] = _skill_source(skill_path)
    return meta
