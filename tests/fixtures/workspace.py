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


def version_release_py(
    version: str,
    py_min: tuple[int, int] | None = (3, 10),
    py_max: tuple[int, int] | None = (3, 13),
) -> str:
    """Mimic odoo/odoo/release.py for a version like `19.0` or `saas-19.4`."""
    serie = version.replace("saas-", "saas~")
    major, minor = serie.rsplit(".", 1)
    major_repr = major if major.isdigit() else repr(major)
    lines = [
        "FINAL, ALPHA = 'final', 'alpha'",
        f"version_info = ({major_repr}, {int(minor)}, 0, FINAL, 0, '')",
        "serie = series = '.'.join(str(v) for v in version_info[:2])",
        "version = serie",
    ]
    if py_min:
        lines.append(f"MIN_PY_VERSION = {py_min!r}")
    if py_max:
        lines.append(f"MAX_PY_VERSION = {py_max!r}")
    return "\n".join(lines) + "\n"
