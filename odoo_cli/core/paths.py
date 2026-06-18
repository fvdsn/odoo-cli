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


# Agent-harness directories, used to install skills only for installed harnesses
# (see specs/agentic_context.md). The config dirs are presence markers; the
# skills dirs are where skills are copied.


def claude_dir(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    return _home(env) / ".claude"


def codex_dir(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    return _home(env) / ".codex"


def opencode_dir(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    return _config_home(env) / "opencode"


def claude_skills_dir(env: Mapping[str, str] | None = None) -> Path:
    return claude_dir(env) / "skills"


def agents_skills_dir(env: Mapping[str, str] | None = None) -> Path:
    """`~/.agents/skills` — read by both Codex and opencode."""
    env = os.environ if env is None else env
    return _home(env) / ".agents" / "skills"
