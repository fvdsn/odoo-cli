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

import os
import shutil
from dataclasses import dataclass, field

from odoo_cli.core import release
from odoo_cli.core.errors import (
    InvalidWorkspace,
    VersionNotFound,
    WorktreeExists,
    WorktreeNotFound,
)
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
    linked: list[str] = field(default_factory=list)
    skipped: list[SkippedRepo] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class AddRepoResult:
    worktree: str
    added: bool
    reason: str = ""


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
        try:
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
        except Exception:
            shutil.rmtree(path, ignore_errors=True)
            self.prune_stale_entries(workspace)
            raise
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

    def create_linked(
        self,
        workspace: Workspace,
        name: str,
        version: str,
        source_name: str,
        addons: list[str],
    ) -> WorktreeCreateResult:
        """Linked worktree: standard repos symlinked from the source
        worktree, addon repositories checked out for real at the root.
        Nothing is stored: the `odoo/` symlink IS the linked marker."""
        validate_name(name, kind="worktree name")
        path = workspace.root / name
        if path.exists():
            raise WorktreeExists(f"{path} already exists")

        source = workspace.root / source_name
        if not (source / "odoo").exists():
            raise WorktreeNotFound(
                f"source worktree '{source_name}' does not exist"
            )
        source_version = self.detect_version(
            Worktree(name=source_name, path=source)
        )
        if release.normalize_version(version) != source_version:
            raise VersionNotFound(
                f"requested version {version} does not match source worktree "
                f"'{source_name}' (detected {source_version})"
            )

        # validate every addon before touching the filesystem
        addon_repos = [self.repositories.get(workspace, a) for a in addons]

        result = WorktreeCreateResult(worktree=Worktree(name=name, path=path))
        path.mkdir(parents=True)
        for repo_name in (*DEFAULT_REPOS, *OPTIONAL_REPOS):
            if (source / repo_name).exists():
                os.symlink(f"../{source_name}/{repo_name}", path / repo_name)
                result.linked.append(repo_name)

        for repo in addon_repos:
            base = version
            if not self.git.branch_exists(repo.path, base):
                base = self.git.default_branch(repo.path)
                result.warnings.append(
                    f"{repo.name}: no branch '{version}', using default "
                    f"branch '{base}'"
                )
            self._checkout(repo.path, path / repo.name, name, base)
            result.checked_out.append(repo.name)
        return result

    def add_repository(
        self, workspace: Workspace, worktree: Worktree, repo_name: str
    ) -> AddRepoResult:
        """Check out an enabled repo into one existing worktree
        (`odoo repo enable` backfill)."""
        if worktree.is_linked:
            return AddRepoResult(
                worktree.name, False,
                f"linked worktree (enable acts on its source "
                f"'{worktree.linked_from}')",
            )
        if (worktree.path / repo_name).exists():
            return AddRepoResult(worktree.name, False, "already present")
        repo = self.repositories.get(workspace, repo_name)
        version = self.detect_version(worktree)
        if not self.git.branch_exists(repo.path, version):
            return AddRepoResult(worktree.name, False, f"no branch '{version}'")
        self._checkout(repo.path, worktree.path / repo_name, worktree.name, version)
        return AddRepoResult(worktree.name, True)

    def is_valid(self, worktree: Worktree) -> bool:
        try:
            self.detect_version(worktree)
        except InvalidWorkspace:
            return False
        return True

    def can_repair_incomplete_full(self, workspace: Workspace, worktree: Worktree) -> bool:
        """True for directories that look like failed CLI-created checkouts.

        We only auto-remove top-level entries matching known repository names,
        which avoids deleting an arbitrary user directory that happens to be
        named like a version.
        """
        if self.is_valid(worktree):
            return False
        if not worktree.path.is_dir() or worktree.path.is_symlink():
            return False
        try:
            entries = [entry for entry in worktree.path.iterdir()]
        except OSError:
            return False
        if not entries:
            return True
        known_repos = {*DEFAULT_REPOS, *OPTIONAL_REPOS}
        for entry in entries:
            if entry.name not in known_repos:
                return False
            if not (entry.is_dir() or entry.is_symlink()):
                return False
        return any((entry / ".git").exists() or entry.is_symlink() for entry in entries)

    def remove_incomplete_full(self, workspace: Workspace, worktree: Worktree) -> None:
        if not self.can_repair_incomplete_full(workspace, worktree):
            raise WorktreeExists(
                f"{worktree.path} exists but is not a valid Odoo worktree",
                hint="move it aside or remove it, then re-run `odoo init`",
            )
        shutil.rmtree(worktree.path)
        self.prune_stale_entries(workspace)

    def prune_stale_entries(self, workspace: Workspace) -> None:
        if not workspace.repositories_dir.is_dir():
            return
        for repo_path in sorted(workspace.repositories_dir.glob("*.git")):
            if repo_path.is_dir():
                self.git.worktree_prune(repo_path)

    def detect_version(self, worktree: Worktree) -> str:
        """Worktree version from the checked-out source (normalized:
        `saas~19.4` -> `saas-19.4`)."""
        return release.normalize_version(
            release.read_release(worktree.path).version
        )
