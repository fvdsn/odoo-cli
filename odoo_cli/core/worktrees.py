"""Worktree discovery and creation.

The filesystem is the authoritative list: a worktree is a top-level workspace
directory containing an `odoo/` entry (directory or symlink). Other top-level
directories are ignored.

Branch convention for checkouts: git refuses to check out one branch in two
worktrees, and several worktrees on the same version is a core use case — so
each worktree checks out a branch named after the worktree, created from the
requested version when the two differ (`odoo worktree create 19.0` checks out
`19.0` itself; `odoo worktree create fix-pos-flow 19.0` creates branch
`fix-pos-flow` from `19.0` in every checked-out repo).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from odoo_cli.core import release
from odoo_cli.core.errors import VersionNotFound, WorktreeExists
from odoo_cli.core.models import Workspace, Worktree
from odoo_cli.core.repositories import (
    DEFAULT_REPOS,
    OPTIONAL_REPOS,
    RepositoryService,
    validate_name,
)
from odoo_cli.util.git import Git


def discover(workspace: Workspace) -> list[Worktree]:
    worktrees = []
    for entry in sorted(workspace.root.iterdir()):
        if entry.name.startswith(".") or not entry.is_dir():
            continue
        odoo_entry = entry / "odoo"
        if odoo_entry.is_dir() or odoo_entry.is_symlink():
            worktrees.append(Worktree(name=entry.name, path=entry))
    return worktrees


@dataclass
class SkippedRepo:
    name: str
    reason: str


@dataclass
class WorktreeCreateResult:
    worktree: Worktree
    checked_out: list[str] = field(default_factory=list)
    skipped: list[SkippedRepo] = field(default_factory=list)


class WorktreeService:
    def __init__(self, git: Git, repositories: RepositoryService):
        self.git = git
        self.repositories = repositories

    def create_full(
        self, workspace: Workspace, name: str, version: str
    ) -> WorktreeCreateResult:
        """Real git worktrees for odoo, documentation, and every optional
        standard repo present in `.repositories/`. Optional repos lacking the
        version are skipped with a warning; odoo lacking it is an error."""
        validate_name(name, kind="worktree name")
        path = workspace.root / name
        if path.exists():
            raise WorktreeExists(f"{path} already exists")

        odoo_repo = self.repositories.get(workspace, "odoo")
        self.repositories.require_version(odoo_repo, version)

        result = WorktreeCreateResult(worktree=Worktree(name=name, path=path))
        path.mkdir(parents=True)
        for repo_name in (*DEFAULT_REPOS, *OPTIONAL_REPOS):
            if not self.repositories.exists(workspace, repo_name):
                continue
            repo = self.repositories.get(workspace, repo_name)
            if not self.repositories.has_version(repo, version):
                result.skipped.append(
                    SkippedRepo(repo_name, f"no branch '{version}'")
                )
                continue
            self._checkout(repo.path, path / repo_name, name, version)
            result.checked_out.append(repo_name)
        return result

    def _checkout(self, repo_path, dest, worktree_name: str, version: str) -> None:
        if worktree_name == version:
            self.git.worktree_add(repo_path, dest, version)
        elif self.git.branch_exists(repo_path, worktree_name):
            # left over from an earlier worktree of the same name: reuse it
            self.git.worktree_add(repo_path, dest, worktree_name)
        else:
            self.git.worktree_add(
                repo_path, dest, worktree_name, new_branch_from=version
            )

    def detect_version(self, worktree: Worktree) -> str:
        """Worktree version from the checked-out source (normalized:
        `saas~19.4` -> `saas-19.4`)."""
        return release.normalize_version(
            release.read_release(worktree.path).version
        )
