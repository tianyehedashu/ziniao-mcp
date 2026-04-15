"""User-level skill management: install/remove skills for AI agents.

``ziniao skill install <name>`` — symlink a discovered skill to agent's global skills directory.
``ziniao skill remove <name>``  — remove a previously installed skill.
``ziniao skill list``           — list all discoverable skills (from repos).
``ziniao skill installed``      — list skills installed for a specific agent.
``ziniao skill agents``         — show supported agents and their directories.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import typer

from ..output import print_result
from .. import get_json_mode

app = typer.Typer(
    no_args_is_help=True,
    help=(
        "Manage AI agent skills (install/remove for Cursor, Trae, etc.). "
        "Skills are discovered from site repos; `install` symlinks them to agent directories."
    ),
)

_HOME = Path.home()

AGENT_SKILLS_DIRS: dict[str, Path] = {
    "trae": _HOME / ".trae" / "skills",
    "cursor": _HOME / ".cursor" / "skills",
    "claude": _HOME / ".claude" / "skills",
    "copilot": _HOME / ".github" / "skills",
    "windsurf": _HOME / ".windsurf" / "skills",
    "codex": _HOME / ".codex" / "skills",
}

DEFAULT_AGENT = "cursor"
AGENT_CHOICES = typer.Option(
    None,
    "--agent", "-a",
    help=f"Target agent (default: {DEFAULT_AGENT}). Use 'all' for every supported agent.",
)


def _resolve_agents(agent: Optional[str]) -> list[tuple[str, Path]]:
    if agent is None:
        agent = DEFAULT_AGENT
    agent = agent.lower().strip()
    if agent == "all":
        return list(AGENT_SKILLS_DIRS.items())
    if agent not in AGENT_SKILLS_DIRS:
        typer.echo(f"Unknown agent '{agent}'. Supported: {', '.join(AGENT_SKILLS_DIRS)}", err=True)
        raise typer.Exit(1)
    return [(agent, AGENT_SKILLS_DIRS[agent])]


def _symlink_skill(source_dir: Path, target_dir: Path) -> None:
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    if target_dir.exists() or target_dir.is_symlink():
        if _is_symlink_or_junction(target_dir):
            target_dir.unlink()
        else:
            raise FileExistsError(
                f"'{target_dir}' exists and is not a symlink/junction. "
                f"Remove it manually first."
            )
    import platform
    if platform.system() == "Windows":
        import subprocess
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(target_dir), str(source_dir)],
            check=True,
            capture_output=True,
        )
    else:
        target_dir.symlink_to(source_dir)


def _is_symlink_or_junction(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def refresh_symlinks(
    *,
    silent_errors: bool = False,
    agent_filter: list[tuple[str, Path]] | None = None,
    reporter: Any | None = None,
) -> int:
    """Re-symlink all ziniao-managed skills across agent directories.

    Returns the number of refreshed symlinks.  Used by both ``skill update``
    and ``site update`` (auto-refresh).

    Args:
        silent_errors: If True, exceptions are swallowed (suitable for
            background/automatic refresh).  If False, errors are re-raised.
        agent_filter: Optional list of ``(name, dir)`` pairs to restrict
            which agents are scanned.  Defaults to all agents.
        reporter: Optional callable ``reporter(agent_name, skill_name, error)``
            invoked on failure when *silent_errors* is True.
    """
    from ...sites.repo import scan_skills

    skills = scan_skills()
    if not skills:
        return 0

    targets = agent_filter or list(AGENT_SKILLS_DIRS.items())
    refreshed = 0
    for agent_name, agent_dir in targets:
        if not agent_dir.is_dir():
            continue
        for d in list(agent_dir.iterdir()):
            if not d.is_dir() or not _is_symlink_or_junction(d):
                continue
            if d.name not in skills:
                continue
            try:
                _symlink_skill(skills[d.name].parent, d)
                refreshed += 1
            except Exception as exc:
                if not silent_errors:
                    raise
                if reporter:
                    reporter(agent_name, d.name, exc)
    return refreshed


@app.command("agents")
def skill_agents() -> None:
    """List supported AI agents and their global skills directories."""
    if get_json_mode():
        print_result({
            "agents": [
                {"name": name, "dir": str(p)} for name, p in AGENT_SKILLS_DIRS.items()
            ]
        }, json_mode=True)
        return
    typer.echo("  Supported AI agents:\n")
    for name, dir_path in AGENT_SKILLS_DIRS.items():
        exists = "✓" if dir_path.is_dir() else " "
        count = len(list(dir_path.iterdir())) if dir_path.is_dir() else 0
        typer.echo(f"  [{exists}]  {name:<12} {dir_path}  ({count} skills)")


@app.command("list")
def skill_list() -> None:
    """List all discoverable skills from registered repos."""
    from ...sites.repo import scan_skills, parse_skill_meta

    skills = scan_skills()
    if not skills:
        typer.echo("  No skills found. Add a repo: ziniao site add <url>")
        return

    if get_json_mode():
        print_result({
            "skills": [parse_skill_meta(p) for p in skills.values()],
            "count": len(skills),
        }, json_mode=True)
        return

    for name, path in sorted(skills.items()):
        meta = parse_skill_meta(path)
        desc = meta.get("description", "")
        if len(desc) > 72:
            desc = desc[:69] + "..."
        typer.echo(f"  {name:<20} {desc}")
    typer.echo(f"\n  Total: {len(skills)}  |  Install: ziniao skill install <name> [--agent cursor]")


@app.command("install")
def skill_install(
    skill_name: str = typer.Argument(..., help="Skill name to install (e.g. rakuten-ads)."),
    agent: Optional[str] = AGENT_CHOICES,
) -> None:
    """Install a skill to an AI agent's global skills directory (symlink).

    Creates a symlink/junction from the agent's skills directory to the
    discovered skill source. Default agent: cursor.

    Examples:
        ziniao skill install rakuten-ads
        ziniao skill install rakuten-ads --agent trae
        ziniao skill install rakuten-ads --agent all
    """
    from ...sites.repo import scan_skills

    skills = scan_skills()
    if skill_name not in skills:
        typer.echo(f"Skill '{skill_name}' not found. Available: {', '.join(sorted(skills)) or '(none)'}", err=True)
        raise typer.Exit(1)

    source_skill_md = skills[skill_name]
    source_dir = source_skill_md.parent

    targets = _resolve_agents(agent)
    for agent_name, agent_dir in targets:
        target = agent_dir / skill_name
        try:
            _symlink_skill(source_dir, target)
            typer.echo(f"  ✓ {skill_name} → {agent_name} ({agent_dir})")
        except Exception as exc:
            typer.echo(f"  ✗ {skill_name} → {agent_name} failed: {exc}", err=True)

    typer.echo(f"\n  Agent will discover '{skill_name}' on next session.")


@app.command("remove")
def skill_remove(
    skill_name: str = typer.Argument(..., help="Skill name to remove."),
    agent: Optional[str] = AGENT_CHOICES,
) -> None:
    """Remove an installed skill from an AI agent's directory.

    Only removes symlinks/junctions created by `ziniao skill install`.
    Default agent: cursor.

    Examples:
        ziniao skill remove rakuten-ads
        ziniao skill remove rakuten-ads --agent trae
        ziniao skill remove rakuten-ads --agent all
    """
    targets = _resolve_agents(agent)
    removed = 0
    for agent_name, agent_dir in targets:
        target = agent_dir / skill_name
        if not target.exists() and not target.is_symlink():
            typer.echo(f"  — {skill_name} not installed for {agent_name}")
            continue
        if not _is_symlink_or_junction(target):
            typer.echo(f"  ✗ {target} is not a symlink/junction, skipping (safety)", err=True)
            continue
        target.unlink()
        typer.echo(f"  ✓ Removed {skill_name} from {agent_name} ({agent_dir})")
        removed += 1

    if removed:
        typer.echo(f"\n  Removed from {removed} agent(s). Restart agent to take effect.")


@app.command("installed")
def skill_installed(
    agent: Optional[str] = AGENT_CHOICES,
) -> None:
    """List skills installed for a specific AI agent.

    Default agent: cursor.

    Examples:
        ziniao skill installed
        ziniao skill installed --agent trae
    """
    targets = _resolve_agents(agent)

    if get_json_mode():
        result = {}
        for agent_name, agent_dir in targets:
            installed = []
            if agent_dir.is_dir():
                for d in sorted(agent_dir.iterdir()):
                    if d.is_dir() and (d / "SKILL.md").is_file():
                        installed.append(d.name)
            result[agent_name] = installed
        print_result(result, json_mode=True)
        return

    for agent_name, agent_dir in targets:
        typer.echo(f"\n  {agent_name} ({agent_dir}):")
        if not agent_dir.is_dir():
            typer.echo("    (directory does not exist)")
            continue
        found = []
        for d in sorted(agent_dir.iterdir()):
            if d.is_dir() and (d / "SKILL.md").is_file():
                link = "→" if _is_symlink_or_junction(d) else " "
                found.append(f"    [{link}] {d.name}")
        if found:
            typer.echo("\n".join(found))
        else:
            typer.echo("    (no skills installed)")


@app.command("update")
def skill_update(
    agent: Optional[str] = AGENT_CHOICES,
) -> None:
    """Re-symlink all ziniao-managed skills for an agent.

    After `ziniao site update` pulls new skill content from repos, run this
    to refresh the symlinks. Also useful if a symlink is broken.

    Default agent: cursor.

    Examples:
        ziniao skill update
        ziniao skill update --agent all
    """
    targets = _resolve_agents(agent)
    errors: list[str] = []

    def _reporter(agent_name: str, skill_name: str, exc: Exception) -> None:
        errors.append(f"  ✗ {agent_name}/{skill_name}: {exc}")

    total = refresh_symlinks(silent_errors=True, agent_filter=targets, reporter=_reporter)

    for agent_name, agent_dir in targets:
        if not agent_dir.is_dir():
            typer.echo(f"  — {agent_name}: directory does not exist, skipping")

    if errors:
        for e in errors:
            typer.echo(e, err=True)

    if total:
        typer.echo(f"\n  Total: {total} skill(s) refreshed. Restart agent to take effect.")
    else:
        typer.echo("\n  No ziniao-managed skills found. Install with: ziniao skill install <name>")
