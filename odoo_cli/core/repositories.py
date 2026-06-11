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
    InvalidWorktreeName,
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

#: Worktree and repository names share these character rules.
NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def validate_name(name: str, *, kind: str = "name") -> None:
    if not name or not NAME_RE.match(name) or name in INTERNAL_DIRS:
        raise InvalidWorktreeName(
            f"invalid {kind} '{name}': use ASCII letters, digits, '_', '-', '.'"
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
        if self.exists(workspace, name):
            raise RepositoryExists(f"repository '{name}' already exists")
        return self._clone(workspace, name, url, full=full)

    def clone_or_fetch(
        self, workspace: Workspace, name: str, url: str | None = None, *, full: bool = False
    ) -> RepositorySpec:
        """Clone a repo, or fetch it when already present (`repo enable`,
        `odoo init` re-runs)."""
        effective_full = full or not self.git.supports_reliable_blobless_clone()
        if self.exists(workspace, name):
            spec = self.get(workspace, name)
            if effective_full and self.git.is_partial_clone(spec.path):
                return self.replace_with_clone(workspace, name, spec.url, full=True)
            if spec.url is None:
                raise RepositoryHasNoRemote(
                    f"repository '{name}' has no origin remote; cannot fetch"
                )
            self.git.fetch(spec.path)
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
        """Replace a bare repository only when no checkout worktrees depend on it."""
        path = workspace.repositories_dir / f"{name}.git"
        resolved_url = url
        if resolved_url is None and path.is_dir():
            resolved_url = self.git.remote_url(path)
        resolved_url = resolved_url or BUILTIN_URLS.get(name)
        if resolved_url is None:
            raise RepositoryHasNoRemote(
                f"repository '{name}' has no origin remote; cannot reclone"
            )
        if path.is_dir() and self._has_checkout_worktrees(path):
            raise OdooCliError(
                f"cannot replace repository '{name}' while worktrees exist",
                hint="remove those worktrees first, or clone a fresh workspace",
            )

        workspace.repositories_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=f".{name}-reclone-", dir=workspace.repositories_dir
        ) as tmp:
            replacement = Path(tmp) / f"{name}.git"
            self.git.clone_bare(resolved_url, replacement, blobless=not full)
            if path.exists():
                shutil.rmtree(path)
            replacement.rename(path)
        return RepositorySpec(name=name, path=path, url=resolved_url)

    def _has_checkout_worktrees(self, repo_path: Path) -> bool:
        repo = repo_path.resolve()
        for path in self.git.worktree_paths(repo_path):
            if path.resolve() != repo:
                return True
        return False

    def has_version(self, repo: RepositorySpec, version: str) -> bool:
        return self.git.branch_exists(repo.path, version)

    def require_version(self, repo: RepositorySpec, version: str) -> None:
        if not self.has_version(repo, version):
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
