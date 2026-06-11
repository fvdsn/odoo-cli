"""Target resolution: which (workspace, worktree, database) a command acts on.

Resolution order (docs/requirements.md → "Target resolution order"):
worktree: explicit --worktree -> cwd inside a worktree -> only worktree -> error
database: explicit --db -> `{worktree}`

Cwd detection uses the logical path ($PWD validated against getcwd()): inside
a linked worktree's symlinked `odoo/`, the physical path points at the source
worktree, but the command must target the linked worktree.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

from odoo_cli.core import worktrees
from odoo_cli.core.errors import TargetAmbiguous, WorktreeNotFound
from odoo_cli.core.models import Target, Workspace, Worktree
from odoo_cli.core.workspace import WorkspaceResolver


class TargetResolver:
    def __init__(
        self,
        workspace_resolver: WorkspaceResolver,
        env: Mapping[str, str] | None = None,
    ):
        self.workspaces = workspace_resolver
        self.env: Mapping[str, str] = os.environ if env is None else env

    def resolve(self, worktree: str | None = None, db: str | None = None) -> Target:
        workspace = self.workspaces.resolve()
        resolved = self._resolve_worktree(workspace, worktree)
        return Target(
            workspace=workspace,
            worktree=resolved,
            database=db or resolved.name,
        )

    def _resolve_worktree(self, workspace: Workspace, name: str | None) -> Worktree:
        available = {wt.name: wt for wt in worktrees.discover(workspace)}

        if name is not None:
            if name not in available:
                raise WorktreeNotFound(
                    f"no worktree named '{name}' in {workspace.root}",
                    hint=self._available_hint(available),
                )
            return available[name]

        cwd_name = self._cwd_worktree_name(workspace.root)
        if cwd_name and cwd_name in available:
            return available[cwd_name]

        if len(available) == 1:
            return next(iter(available.values()))
        if not available:
            raise WorktreeNotFound(
                f"no worktrees in {workspace.root}",
                hint="create one with `odoo worktree create <version>`",
            )
        raise TargetAmbiguous(
            "multiple worktrees exist and no default is configured",
            hint=(
                f"{self._available_hint(available)}; run the command from "
                "inside a worktree or pass --worktree"
            ),
        )

    def _available_hint(self, available: dict[str, Worktree]) -> str:
        names = ", ".join(sorted(available)) or "(none)"
        return f"available worktrees: {names}"

    def _cwd_worktree_name(self, root: Path) -> str | None:
        """First path component below the workspace root, from the logical cwd."""
        cwd = self._logical_cwd()
        for base in (root, root.resolve()):
            try:
                rel = cwd.relative_to(base)
            except ValueError:
                continue
            if rel.parts:
                return rel.parts[0]
        return None

    def _logical_cwd(self) -> Path:
        """$PWD when it still points at the current directory, else getcwd().

        getcwd() is physical (symlinks resolved); $PWD preserves the path the
        user navigated through, which is what identifies a linked worktree.
        """
        physical = Path.cwd()
        pwd = self.env.get("PWD")
        if pwd:
            logical = Path(pwd)
            try:
                if logical.resolve() == physical:
                    return logical
            except OSError:
                pass
        return physical
