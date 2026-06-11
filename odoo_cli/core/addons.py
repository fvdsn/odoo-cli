"""Deterministic addons-path resolution from the worktree layout.

There is no `addons = [...]` list anywhere: this only reads the filesystem.
Order (docs/requirements.md): `odoo/addons`, `themes` if present, `enterprise`
if present, then custom addon paths sorted alphabetically. Duplicate module
names across paths are left to odoo-bin's own resolution rules.
"""

from __future__ import annotations

from pathlib import Path

from odoo_cli.core.models import Worktree
from odoo_cli.core.repositories import NON_ADDON_REPOS

#: Standard repos handled by the fixed-order rules above, never scanned as
#: custom addon directories.
_STANDARD_ENTRIES = ("odoo", "enterprise", "themes", *NON_ADDON_REPOS)


def resolve_addons_paths(worktree: Worktree) -> list[Path]:
    paths = [worktree.path / "odoo" / "addons"]
    for name in ("themes", "enterprise"):
        if (worktree.path / name).is_dir():
            paths.append(worktree.path / name)
    paths.extend(sorted(_custom_paths(worktree), key=str))
    return paths


def _custom_paths(worktree: Worktree) -> set[Path]:
    custom: set[Path] = set()
    for entry in worktree.path.iterdir():
        if entry.name.startswith(".") or entry.name in _STANDARD_ENTRIES:
            continue
        if not entry.is_dir():
            continue
        if (entry / "__manifest__.py").is_file():
            # a single-addon directory: add the worktree root so odoo-bin
            # discovers the addon by its directory name
            custom.add(worktree.path)
        elif _has_addon_children(entry):
            custom.add(entry)
    return custom


def _has_addon_children(directory: Path) -> bool:
    return any(
        (child / "__manifest__.py").is_file()
        for child in directory.iterdir()
        if child.is_dir() and not child.name.startswith(".")
    )
