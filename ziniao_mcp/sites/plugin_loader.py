"""Site plugin discovery.

``get_plugin(site_name)`` finds a :class:`SitePlugin` subclass in this order:
user-local file → repo dirs → builtin package ``ziniao_mcp.sites.<site>`` →
entry_points.  Builtin plugins use normal package import so relative imports
work; file-only loading is used for user-local and repo plugins.
"""

from __future__ import annotations

from pathlib import Path

from ._base import SitePlugin
from .discovery import BUILTIN_DIR, USER_DIR


def get_plugin(site_name: str) -> SitePlugin | None:
    """Try to load a ``SitePlugin`` subclass for *site_name*.

    Returns ``None`` if no plugin is defined (JSON-only preset).
    """
    user_init = USER_DIR / site_name / "__init__.py"
    if user_init.is_file():
        loaded = _load_plugin_from_file(user_init, site_name)
        if loaded is not None:
            return loaded

    from . import repo as _repo_mod  # pylint: disable=import-outside-toplevel
    if _repo_mod.REPOS_DIR.is_dir():
        for repo_dir in sorted(_repo_mod.REPOS_DIR.iterdir()):
            if not repo_dir.is_dir() or repo_dir.name.startswith((".", "_")):
                continue
            if repo_dir.name == "__pycache__":
                continue
            repo_init = repo_dir / site_name / "__init__.py"
            if repo_init.is_file():
                loaded = _load_plugin_from_file(repo_init, site_name)
                if loaded is not None:
                    return loaded

    if (BUILTIN_DIR / site_name / "__init__.py").is_file():
        import importlib  # pylint: disable=import-outside-toplevel

        try:
            mod = importlib.import_module(f"ziniao_mcp.sites.{site_name}")
        except ModuleNotFoundError:
            pass
        else:
            explicit = getattr(mod, "SITE_PLUGIN", None)
            if explicit is not None:
                if not (isinstance(explicit, type) and issubclass(explicit, SitePlugin) and explicit is not SitePlugin):
                    raise TypeError(f"{mod.__name__}.SITE_PLUGIN must be a SitePlugin subclass")
                return explicit()
            subs: list[type] = []
            for attr in dir(mod):
                obj = getattr(mod, attr)
                if isinstance(obj, type) and issubclass(obj, SitePlugin) and obj is not SitePlugin:
                    subs.append(obj)
            if len(subs) == 1:
                return subs[0]()
            if len(subs) > 1:
                names = ", ".join(s.__name__ for s in subs)
                raise ValueError(
                    f"Sites package {site_name!r} defines multiple SitePlugin classes ({names}); set SITE_PLUGIN"
                )

    try:
        from importlib.metadata import entry_points  # pylint: disable=import-outside-toplevel
        eps = entry_points()
        group = eps.get("ziniao.sites", []) if isinstance(eps, dict) else eps.select(group="ziniao.sites")
        for ep in group:
            if ep.name == site_name:
                cls = ep.load()
                if isinstance(cls, type) and issubclass(cls, SitePlugin):
                    return cls()
    except Exception:
        pass
    return None


def _load_plugin_from_file(path: Path, site_name: str) -> SitePlugin | None:
    """Import a Python file and return the first ``SitePlugin`` subclass instance."""
    import importlib.util  # pylint: disable=import-outside-toplevel

    spec = importlib.util.spec_from_file_location(f"ziniao_site_{site_name}", path)
    if not spec or not spec.loader:
        return None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception:
        return None
    for attr in dir(mod):
        obj = getattr(mod, attr)
        if isinstance(obj, type) and issubclass(obj, SitePlugin) and obj is not SitePlugin:
            return obj()
    return None
