"""Temp-workspace builder for unit tests.

Creates an isolated HOME with a valid workspace marker and returns the env
mapping services expect. Nothing here touches the user's real ~/odoo.
"""

from __future__ import annotations

import os
from pathlib import Path


def make_env(home: Path, **extra: str) -> dict[str, str]:
    env = {"HOME": str(home)}
    env.update(extra)
    return env


def make_workspace(home: Path, *, repos: tuple[str, ...] = ("odoo", "documentation")) -> Path:
    """Create `~/odoo` with bare-repo marker directories (no real git)."""
    root = home / "odoo"
    for name in (".repositories", ".venvs", ".run"):
        (root / name).mkdir(parents=True, exist_ok=True)
    for repo in repos:
        (root / ".repositories" / f"{repo}.git").mkdir(exist_ok=True)
    return root


def make_worktree(
    root: Path,
    name: str,
    *,
    version: str | None = None,
    linked_from: str | None = None,
    repos: tuple[str, ...] = ("documentation",),
) -> Path:
    """Create a worktree directory: full (real odoo/ dir with release.py) or
    linked (odoo/ symlinked from another worktree)."""
    path = root / name
    path.mkdir(parents=True, exist_ok=True)
    if linked_from:
        for repo in ("odoo", *repos):
            source = root / linked_from / repo
            if source.exists() and not (path / repo).is_symlink():
                os.symlink(f"../{linked_from}/{repo}", path / repo)
    else:
        release = path / "odoo" / "odoo" / "release.py"
        release.parent.mkdir(parents=True, exist_ok=True)
        if version:
            release.write_text(version_release_py(version))
        for repo in repos:
            (path / repo).mkdir(exist_ok=True)
    return path


def version_release_py(version: str) -> str:
    series = version.replace("saas~", "").replace("saas-", "")
    return (
        f"version_info = ({series.split('.')[0]}, 0, 0, 'final', 0, '')\n"
        f"version = '{version}'\n"
        f"serie = '{version}'\n"
        "MIN_PY_VERSION = (3, 10)\n"
        "MAX_PY_VERSION = (3, 13)\n"
    )
