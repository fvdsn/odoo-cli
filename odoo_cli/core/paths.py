"""Well-known path resolution.

Functions take an env mapping (default: os.environ) so tests can isolate
HOME/ODOO_DIR/XDG_CONFIG_HOME without touching the real environment.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path


def _home(env: Mapping[str, str]) -> Path:
    home = env.get("HOME")
    return Path(home) if home else Path.home()


def workspace_root(env: Mapping[str, str] | None = None) -> Path:
    """`ODOO_DIR` if set, otherwise `~/odoo`. No parent-walking."""
    env = os.environ if env is None else env
    odoo_dir = env.get("ODOO_DIR")
    if odoo_dir:
        return Path(odoo_dir).expanduser()
    return _home(env) / "odoo"


def _config_home(env: Mapping[str, str]) -> Path:
    """`$XDG_CONFIG_HOME` if set, otherwise `~/.config` (as odoo-bin resolves)."""
    xdg = env.get("XDG_CONFIG_HOME")
    return Path(xdg) if xdg else _home(env) / ".config"


def odoo_conf_path(env: Mapping[str, str] | None = None) -> Path:
    """Odoo's standard config location: `~/.config/odoo/odoo.conf`.

    Honors XDG_CONFIG_HOME like odoo-bin's own resolution does, so manual
    odoo-bin runs share the same file.
    """
    env = os.environ if env is None else env
    return _config_home(env) / "odoo" / "odoo.conf"


# Agent-harness directories (see specs/agentic_context.md). These are the home
# dirs used only to *detect* Claude — skills install into the workspace, not
# here (see core/agent_assets.py). The config dirs are presence markers.


def claude_dir(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    return _home(env) / ".claude"


def claude_desktop_dirs(env: Mapping[str, str] | None = None) -> list[Path]:
    """Config dirs of the Claude **desktop** app, used only as a presence
    signal. The desktop app hosts Claude Code (which reads `~/.claude/skills`
    and `CLAUDE.md`), so it justifies the Claude-only assets even when the
    `claude` CLI is absent from PATH. Paths are platform-specific; one that does
    not apply to the current OS simply never exists.
    """
    env = os.environ if env is None else env
    dirs = [
        _home(env) / "Library" / "Application Support" / "Claude",  # macOS
        _config_home(env) / "Claude",  # Linux (honors XDG_CONFIG_HOME)
    ]
    appdata = env.get("APPDATA")
    if appdata:
        dirs.append(Path(appdata) / "Claude")  # Windows
    return dirs
