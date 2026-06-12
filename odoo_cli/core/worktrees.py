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
    OdooCliError,
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
    #: The worktree already existed; only missing entries were added.
    existed: bool = False


@dataclass
class AddRepoResult:
    worktree: str
    added: bool
    reason: str = ""


class WorktreeService:
    def __init__(self, git: Git, repositories: RepositoryService):
        self.git = git
        self.repositories = repositories

    def _prepare_create(
        self, workspace: Workspace, name: str
    ) -> tuple[Worktree, list[str], bool]:
        """Shared pre-create handling: validate the name, repair leftovers of
        an interrupted creation, and prune stale git registrations (a
        manually deleted worktree directory otherwise blocks re-creation).

        Returns (worktree, warnings, existed). `existed` means a valid
        worktree is already there: the caller switches to completion mode
        and adds only what is missing — a valid worktree may hold work and
        is never removed."""
        validate_name(name, kind="worktree name")
        path = workspace.root / name
        worktree = Worktree(name=name, path=path)
        warnings: list[str] = []
        if path.exists() or path.is_symlink():
            if self.is_valid(worktree):
                return worktree, warnings, True
            if not self.can_repair_incomplete(workspace, worktree):
                raise WorktreeExists(
                    f"{path} exists but is not a valid Odoo worktree",
                    hint="move it aside or remove it, then re-run",
                )
            self.remove_incomplete(workspace, worktree)
            warnings.append(
                f"{path} was incomplete (interrupted creation?); recreating it"
            )
        else:
            self.prune_stale_entries(workspace)
        return worktree, warnings, False

    def create_full(
        self, workspace: Workspace, name: str, version: str
    ) -> WorktreeCreateResult:
        """Real git worktrees for odoo, documentation, and every optional
        standard repo present in `.repositories/`. Optional repos lacking the
        version are skipped with a warning; odoo lacking it is an error.

        Re-running on an existing valid worktree completes it: missing
        standard checkouts are added, present ones are never touched."""
        worktree, warnings, existed = self._prepare_create(workspace, name)
        path = worktree.path
        if existed:
            return self._complete_full(workspace, worktree, version, warnings)

        odoo_repo = self.repositories.get(workspace, "odoo")
        self.repositories.require_version(odoo_repo, version)

        result = WorktreeCreateResult(worktree=worktree, warnings=warnings)
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
        except BaseException:
            # BaseException: Ctrl-C must roll back too. Best effort — when
            # the rollback itself is interrupted, _prepare_create repairs
            # the leftovers on the next run.
            shutil.rmtree(path, ignore_errors=True)
            self.prune_stale_entries(workspace)
            raise
        return result

    def _complete_full(
        self,
        workspace: Workspace,
        worktree: Worktree,
        version: str,
        warnings: list[str],
    ) -> WorktreeCreateResult:
        """Add the standard checkouts missing from an existing full worktree
        (e.g. a create interrupted after `odoo` finished)."""
        if worktree.is_linked:
            raise WorktreeExists(
                f"worktree '{worktree.name}' already exists and is linked",
                hint="re-run with --linked-from to complete it",
            )
        detected = self.detect_version(worktree)
        if release.normalize_version(version) != detected:
            raise WorktreeExists(
                f"worktree '{worktree.name}' already exists on version "
                f"{detected}, not {version}"
            )
        result = WorktreeCreateResult(
            worktree=worktree, warnings=warnings, existed=True
        )
        for repo_name in (*DEFAULT_REPOS, *OPTIONAL_REPOS):
            dest = worktree.path / repo_name
            if dest.exists() or dest.is_symlink():
                continue
            if not self.repositories.exists(workspace, repo_name):
                continue
            added = self.add_repository(workspace, worktree, repo_name)
            if added.added:
                result.checked_out.append(repo_name)
            else:
                result.skipped.append(SkippedRepo(repo_name, added.reason))
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
        standard = {*DEFAULT_REPOS, *OPTIONAL_REPOS}
        for addon in addons:
            if addon in standard:
                raise OdooCliError(
                    f"'{addon}' is a standard repository, not an addon",
                    hint=(
                        "standard repos are symlinked from the source "
                        "worktree; --addon takes repositories added with "
                        "`odoo repo add`"
                    ),
                )
        worktree, warnings, existed = self._prepare_create(workspace, name)
        path = worktree.path

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

        if existed:
            return self._complete_linked(
                worktree, version, source_name, addon_repos, warnings
            )

        result = WorktreeCreateResult(worktree=worktree, warnings=warnings)
        path.mkdir(parents=True)
        try:
            for repo_name in (*DEFAULT_REPOS, *OPTIONAL_REPOS):
                if (source / repo_name).exists():
                    os.symlink(f"../{source_name}/{repo_name}", path / repo_name)
                    result.linked.append(repo_name)

            for repo in addon_repos:
                base = self._addon_base(repo, version, result)
                self._checkout(repo.path, path / repo.name, name, base)
                result.checked_out.append(repo.name)
        except BaseException:
            # BaseException: see create_full
            shutil.rmtree(path, ignore_errors=True)
            self.prune_stale_entries(workspace)
            raise
        return result

    def _complete_linked(
        self,
        worktree: Worktree,
        version: str,
        source_name: str,
        addon_repos: list,
        warnings: list[str],
    ) -> WorktreeCreateResult:
        """Add the symlinks and addon checkouts missing from an existing
        linked worktree (e.g. a create interrupted mid-checkout)."""
        if not worktree.is_linked:
            raise WorktreeExists(
                f"worktree '{worktree.name}' already exists as a full worktree"
            )
        if worktree.linked_from != source_name:
            raise WorktreeExists(
                f"worktree '{worktree.name}' is linked from "
                f"'{worktree.linked_from}', not '{source_name}'"
            )
        path = worktree.path
        source = path.parent / source_name
        result = WorktreeCreateResult(
            worktree=worktree, warnings=warnings, existed=True
        )
        for repo_name in (*DEFAULT_REPOS, *OPTIONAL_REPOS):
            dest = path / repo_name
            if dest.exists() or dest.is_symlink():
                continue
            if (source / repo_name).exists():
                os.symlink(f"../{source_name}/{repo_name}", dest)
                result.linked.append(repo_name)
        for repo in addon_repos:
            dest = path / repo.name
            if dest.exists() or dest.is_symlink():
                continue
            base = self._addon_base(repo, version, result)
            self.git.worktree_prune(repo.path)
            try:
                self._checkout(repo.path, dest, worktree.name, base)
            except BaseException:
                # only the failed checkout is rolled back: the worktree is
                # valid and may hold work, so it is never removed here
                shutil.rmtree(dest, ignore_errors=True)
                self.git.worktree_prune(repo.path)
                raise
            result.checked_out.append(repo.name)
        return result

    def _addon_base(self, repo, version: str, result: WorktreeCreateResult) -> str:
        """The branch an addon checkout starts from: the Odoo version branch
        when the repo has it, its default branch (with a warning) otherwise."""
        if self.git.branch_exists(repo.path, version):
            return version
        base = self.git.default_branch(repo.path)
        result.warnings.append(
            f"{repo.name}: no branch '{version}', using default branch '{base}'"
        )
        return base

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
        dest = worktree.path / repo_name
        repo = self.repositories.get(workspace, repo_name)
        # is_symlink first: exists() follows links, so a dangling symlink
        # would fall through every check into `git worktree add`
        if dest.is_symlink() or dest.exists():
            if dest.is_symlink():
                if not dest.exists():
                    return AddRepoResult(
                        worktree.name, False,
                        f"{dest} is a broken symlink; remove it and re-run",
                    )
                return AddRepoResult(worktree.name, False, "already present")
            if (dest / ".git").exists():
                # present, but is it a checkout of the expected repository?
                common = self.git.common_dir(dest)
                if common is not None and common.is_relative_to(
                    repo.path.resolve()
                ):
                    return AddRepoResult(worktree.name, False, "already present")
                return AddRepoResult(
                    worktree.name, False,
                    f"{dest} is a checkout of a different repository; "
                    "move it aside and re-run",
                )
            # exists but is no usable checkout (e.g. an earlier failed add):
            # don't let it poison every retry, but don't delete user data
            return AddRepoResult(
                worktree.name, False,
                f"{dest} exists but is not a git checkout; remove it and re-run",
            )
        version = self.detect_version(worktree)
        if not self.git.branch_exists(repo.path, version):
            return AddRepoResult(worktree.name, False, f"no branch '{version}'")
        # a stale registration (manually deleted checkout) blocks worktree add
        self.git.worktree_prune(repo.path)
        try:
            self._checkout(repo.path, dest, worktree.name, version)
        except BaseException:
            # BaseException: see create_full
            shutil.rmtree(dest, ignore_errors=True)
            self.git.worktree_prune(repo.path)
            raise
        return AddRepoResult(worktree.name, True)

    def is_valid(self, worktree: Worktree) -> bool:
        try:
            self.detect_version(worktree)
        except InvalidWorkspace:
            return False
        return True

    def can_repair_incomplete(self, workspace: Workspace, worktree: Worktree) -> bool:
        """True for directories that are provably leftovers of an interrupted
        CLI worktree creation, full or linked.

        Acceptable entries: symlinks (the linked layout, dangling included),
        checkouts backed by a bare repo under `.repositories/` (addon
        checkouts only count when the linked `odoo/` symlink signature is
        present), and bare known-repo-named directories. Anything else might
        be user data and is never auto-removed.
        """
        if self.is_valid(worktree):
            return False
        if not worktree.path.is_dir() or worktree.path.is_symlink():
            return False
        try:
            entries = list(worktree.path.iterdir())
        except OSError:
            return False
        if not entries:
            return True
        repos_root = workspace.repositories_dir.resolve()
        known_repos = {*DEFAULT_REPOS, *OPTIONAL_REPOS}
        linked_layout = (worktree.path / "odoo").is_symlink()
        saw_checkout = False
        for entry in entries:
            if entry.is_symlink():
                saw_checkout = True
                continue
            if not entry.is_dir():
                return False
            if (entry / ".git").exists():
                if entry.name in known_repos:
                    # standard-repo name + .git: the classic interrupted
                    # checkout (the gitdir may itself be broken)
                    saw_checkout = True
                    continue
                if not linked_layout:
                    return False
                # addon checkout in a linked layout: only removable when
                # provably backed by one of our bare repos
                common = self.git.common_dir(entry)
                if common is None or not common.is_relative_to(repos_root):
                    return False  # a checkout of something else: user data
                saw_checkout = True
                continue
            if entry.name in known_repos:
                continue  # partial directory left before git wrote .git
            return False
        return saw_checkout

    def remove_incomplete(self, workspace: Workspace, worktree: Worktree) -> None:
        if not self.can_repair_incomplete(workspace, worktree):
            raise WorktreeExists(
                f"{worktree.path} exists but is not a valid Odoo worktree",
                hint="move it aside or remove it, then re-run",
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
