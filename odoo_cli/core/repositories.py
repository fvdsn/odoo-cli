"""Repository management: bare clones under `.repositories/`.

The directory is the registry: a repository is "enabled" iff
`.repositories/{name}.git` exists; its URL is the bare repo's `origin`
remote. Nothing is stored elsewhere.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path

from odoo_cli.core.errors import (
    InvalidName,
    OdooCliError,
    RepositoryExists,
    RepositoryHasNoRemote,
    RepositoryNotFound,
    VersionNotFound,
)
from odoo_cli.core.models import INTERNAL_DIRS, RepositorySpec, Workspace
from odoo_cli.util.git import Git

#: Cloned by `odoo init`.
DEFAULT_REPOS = ("odoo", "documentation")

#: Optional builtins, cloned via `odoo repo enable`.
OPTIONAL_REPOS = ("enterprise", "themes", "upgrade")

#: Repositories that never contribute addons paths.
NON_ADDON_REPOS = ("documentation", "upgrade")

BUILTIN_URLS = {
    "odoo": "https://github.com/odoo/odoo.git",
    "documentation": "https://github.com/odoo/documentation.git",
    "enterprise": "git@github.com:odoo/enterprise.git",
    "themes": "https://github.com/odoo/design-themes.git",
    "upgrade": "git@github.com:odoo/upgrade.git",
}

#: Worktree, repository, and database names share these character rules.
#: The first character may not be '-' or '.': these names end up as argv
#: positionals (createdb, dropdb, psql) and must never look like options;
#: this also excludes the path specials '.' and '..'.
NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")


def validate_name(name: str, *, kind: str = "name") -> None:
    if not name or not NAME_RE.match(name) or name in INTERNAL_DIRS:
        raise InvalidName(
            f"invalid {kind} '{name}': use ASCII letters, digits, '_', '-', "
            "'.', starting with a letter, digit, or '_'"
        )


class RepositoryService:
    def __init__(self, git: Git):
        self.git = git

    def list(self, workspace: Workspace) -> list[RepositorySpec]:
        repos = []
        if not workspace.repositories_dir.is_dir():
            return repos
        for entry in sorted(workspace.repositories_dir.iterdir()):
            if entry.is_dir() and entry.name.endswith(".git"):
                name = entry.name[: -len(".git")]
                repos.append(
                    RepositorySpec(name=name, path=entry, url=self.git.remote_url(entry))
                )
        return repos

    def get(self, workspace: Workspace, name: str) -> RepositorySpec:
        path = workspace.repositories_dir / f"{name}.git"
        if not path.is_dir():
            raise RepositoryNotFound(
                f"repository '{name}' is not in {workspace.repositories_dir}",
                hint="clone it with `odoo repo add` or `odoo repo enable`",
            )
        return RepositorySpec(name=name, path=path, url=self.git.remote_url(path))

    def exists(self, workspace: Workspace, name: str) -> bool:
        return (workspace.repositories_dir / f"{name}.git").is_dir()

    def is_corrupt(self, workspace: Workspace, name: str) -> bool:
        """An existing bare repo without a resolvable HEAD: the leftover of
        an interrupted clone (or manual damage). Unusable for every purpose
        and safe to replace — no worktree can be attached to it."""
        if not self.exists(workspace, name):
            return False
        return not self.git.has_valid_head(
            workspace.repositories_dir / f"{name}.git"
        )

    def add(
        self, workspace: Workspace, name: str, url: str, *, full: bool = False
    ) -> RepositorySpec:
        """`odoo repo add`: clone a custom addon repository."""
        validate_name(name, kind="repository name")
        if name in BUILTIN_URLS:
            raise RepositoryExists(
                f"'{name}' is a built-in repository",
                hint=f"use `odoo repo enable {name}`",
            )
        if self.is_corrupt(workspace, name):
            # leftover of an interrupted clone: a re-run must repair it
            return self.replace_with_clone(workspace, name, url, full=full)
        if self.exists(workspace, name):
            raise RepositoryExists(f"repository '{name}' already exists")
        return self._clone(workspace, name, url, full=full)

    def clone_or_fetch(
        self, workspace: Workspace, name: str, url: str | None = None, *, full: bool = False
    ) -> RepositorySpec:
        """Clone a repo, or fetch it when already present (`repo enable`,
        `odoo init` re-runs). A corrupt leftover of an interrupted clone is
        replaced, so a re-run always converges to a usable repository."""
        effective_full = full or not self.git.supports_reliable_blobless_clone()
        if self.is_corrupt(workspace, name):
            return self.replace_with_clone(
                workspace, name, url, full=effective_full
            )
        if self.exists(workspace, name):
            spec = self.get(workspace, name)
            if effective_full and self.git.is_partial_clone(spec.path):
                if full:
                    # explicit --full: convert, or refuse loudly when
                    # worktrees depend on the repo (replace_with_clone raises)
                    return self.replace_with_clone(
                        workspace, name, spec.url, full=True
                    )
                if not self._has_checkout_worktrees(spec.path):
                    # old git, partial repo, nothing depends on it: upgrade
                    return self.replace_with_clone(
                        workspace, name, spec.url, full=True
                    )
                # old git but the partial repo demonstrably works (worktrees
                # attached): keep it and fetch — recloning happens only when
                # a checkout actually fails (promisor retry)
            if spec.url is None:
                raise RepositoryHasNoRemote(
                    f"repository '{name}' has no origin remote; cannot fetch"
                )
            # branches checked out in worktrees belong to those worktrees
            # (git would refuse to update them and abort the whole fetch)
            self.git.fetch(
                spec.path,
                exclude_branches=self.git.worktree_branches(spec.path),
            )
            return spec
        resolved_url = url or BUILTIN_URLS.get(name)
        if resolved_url is None:
            raise RepositoryNotFound(f"no URL known for repository '{name}'")
        return self._clone(workspace, name, resolved_url, full=effective_full)

    def _clone(self, workspace: Workspace, name: str, url: str, *, full: bool) -> RepositorySpec:
        workspace.repositories_dir.mkdir(parents=True, exist_ok=True)
        path = workspace.repositories_dir / f"{name}.git"
        blobless = not full and self.git.supports_reliable_blobless_clone()
        self.git.clone_bare(url, path, blobless=blobless)
        return RepositorySpec(name=name, path=path, url=url)

    def replace_with_clone(
        self,
        workspace: Workspace,
        name: str,
        url: str | None = None,
        *,
        full: bool,
    ) -> RepositorySpec:
        """Replace a bare repository only when no checkout worktrees depend on it.

        Interruption-safe ordering: clone into a temp dir first, swap the old
        repo aside and the new one in with two renames, and delete the old
        copy only at the end. The slow deletions never sit between the user
        and a usable repository."""
        path = workspace.repositories_dir / f"{name}.git"
        resolved_url = url
        if resolved_url is None and path.is_dir():
            resolved_url = self.git.remote_url(path)  # None for a broken repo
        resolved_url = resolved_url or BUILTIN_URLS.get(name)
        if resolved_url is None:
            raise RepositoryHasNoRemote(
                f"repository '{name}' has no origin remote; cannot reclone",
                hint=f"remove {path} and clone it again with an explicit URL",
            )
        usable = path.is_dir() and self.git.has_valid_head(path)
        if usable and self._has_checkout_worktrees(path):
            raise OdooCliError(
                f"cannot replace repository '{name}' while worktrees exist",
                hint="remove those worktrees first, or clone a fresh workspace",
            )

        workspace.repositories_dir.mkdir(parents=True, exist_ok=True)
        old = workspace.repositories_dir / f".{name}.git.old"
        if old.exists():
            shutil.rmtree(old)  # leftover of an interrupted replace
        with tempfile.TemporaryDirectory(
            prefix=f".{name}-reclone-", dir=workspace.repositories_dir
        ) as tmp:
            replacement = Path(tmp) / f"{name}.git"
            self.git.clone_bare(resolved_url, replacement, blobless=not full)
            if path.exists():
                path.rename(old)
            try:
                replacement.rename(path)
            except BaseException:
                if old.exists() and not path.exists():
                    old.rename(path)  # restore the original
                raise
        if old.exists():
            shutil.rmtree(old)
        return RepositorySpec(name=name, path=path, url=resolved_url)

    def _has_checkout_worktrees(self, repo_path: Path) -> bool:
        repo = repo_path.resolve()
        for path in self.git.worktree_paths(repo_path):
            if path.resolve() != repo:
                return True
        return False

    def clone_mode(self, full: bool) -> str:
        """The effective strategy for display: old git silently forces full
        clones, and the output must not claim otherwise."""
        if full:
            return "full"
        if not self.git.supports_reliable_blobless_clone():
            return "full: this git version has unreliable blobless clones"
        return "blobless"

    def has_version(self, repo: RepositorySpec, version: str) -> bool:
        return self.git.branch_exists(repo.path, version)

    def require_version(self, repo: RepositorySpec, version: str) -> None:
        if self.has_version(repo, version):
            return
        if not self.git.has_valid_head(repo.path):
            raise VersionNotFound(
                f"repository '{repo.name}' looks incomplete (interrupted "
                "clone?)",
                hint="re-run `odoo init` to repair it",
            )
        raise VersionNotFound(
            f"repository '{repo.name}' has no branch '{version}'"
        )

    def latest_stable_version(self, repo: RepositorySpec) -> str:
        """Highest `N.0` branch — `odoo init`'s default version."""
        stable = [
            branch
            for branch in self.git.list_branches(repo.path)
            if re.fullmatch(r"\d+\.0", branch)
        ]
        if not stable:
            raise VersionNotFound(
                f"repository '{repo.name}' has no stable N.0 branch"
            )
        return max(stable, key=lambda b: int(b.split(".")[0]))
