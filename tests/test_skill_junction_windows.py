"""Regression: dangling directory junction must be replaced (Windows)."""

from __future__ import annotations

import platform
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(platform.system() != "Windows", reason="Windows junctions only")


def test_symlink_skill_replaces_dangling_junction(tmp_path: Path) -> None:
    from ziniao_mcp.cli.commands.skill_cmd import _symlink_skill

    old_target = tmp_path / "old_target"
    old_target.mkdir()
    (old_target / "SKILL.md").write_text("old", encoding="utf-8")
    link = tmp_path / "site-development"
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(old_target)],
        check=True,
        capture_output=True,
    )
    shutil.rmtree(old_target)

    new_source = tmp_path / "new_source"
    new_source.mkdir()
    (new_source / "SKILL.md").write_text("new", encoding="utf-8")

    _symlink_skill(new_source, link)

    assert link.is_dir()
    assert (link / "SKILL.md").read_text(encoding="utf-8") == "new"
    assert Path(link).resolve() == new_source.resolve()
