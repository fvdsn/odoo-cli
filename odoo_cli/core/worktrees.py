"""Worktree discovery (creation arrives with WorktreeService).

The filesystem is the authoritative list: a worktree is a top-level workspace
directory containing an `odoo/` entry (directory or symlink). Other top-level
directories are ignored.
"""

from __future__ import annotations

from odoo_cli.core.models import Workspace, Worktree


def discover(workspace: Workspace) -> list[Worktree]:
    worktrees = []
    for entry in sorted(workspace.root.iterdir()):
        if entry.name.startswith(".") or not entry.is_dir():
            continue
        odoo_entry = entry / "odoo"
        if odoo_entry.is_dir() or odoo_entry.is_symlink():
            worktrees.append(Worktree(name=entry.name, path=entry))
    return worktrees
