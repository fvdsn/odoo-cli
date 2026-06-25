"""Target resolution: which (workspace, worktree, database) a command acts on.

Resolution order (specs/requirements.md → "Target resolution order"):
worktree: explicit --worktree -> cwd inside a worktree -> `-d` hint
          -> only worktree -> error
database: explicit --db -> `{worktree}`

The `-d` hint: a worktree named like the database (every worktree's default
db is its own name), else the single worktree holding run state for that db
(`.run/{worktree}/{db}/ports`). The name match wins because it is a stable
convention, while run state accumulates over time.

Cwd detection uses the logical path ($PWD validated against getcwd()): inside
a linked worktree's symlinked `odoo/`, the physical path points at the source
worktree, but the command must target the linked worktree.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from odoo_cli.core import worktrees
from odoo_cli.core.errors import TargetAmbiguous, WorktreeNotFound
from odoo_cli.core.models import Target, Workspace, Worktree
from odoo_cli.core.repositories import validate_name
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
        if db is not None:
            # validated before any use: the worktree hint below builds
            # filesystem paths from it
            validate_name(db, kind="database name")
        workspace = self.workspaces.resolve()
        resolved = self._resolve_worktree(workspace, worktree, db)
        database = db or resolved.name
        # db names reach psql command lines and SQL literals; the default
        # (worktree name) needs this too — discovery trusts the filesystem,
        # so a manually created directory may carry any character
        validate_name(database, kind="database name")
        return Target(
            workspace=workspace,
            worktree=resolved,
            database=database,
        )

    def _resolve_worktree(
        self, workspace: Workspace, name: str | None, db: str | None = None
    ) -> Worktree:
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

        if db is not None and len(available) > 1:
            hinted = self._db_hinted_worktree(workspace, available, db)
            if hinted is not None:
                return hinted

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

    def _db_hinted_worktree(
        self, workspace: Workspace, available: dict[str, Worktree], db: str
    ) -> Worktree | None:
        if db in available:
            return available[db]
        ran = [
            wt
            for wt in available
            if (workspace.run_dir / wt / db / "ports").is_file()
        ]
        if len(ran) == 1:
            return available[ran[0]]
        if len(ran) > 1:
            raise TargetAmbiguous(
                f"database '{db}' has run under several worktrees: "
                f"{', '.join(sorted(ran))}",
                hint="pass --worktree to pick one",
            )
        return None

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
