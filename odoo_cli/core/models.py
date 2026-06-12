"""Core value objects (docs/architecture.md → "Core data model").

Dataclasses carried across services. They hold paths and derived facts, no
behavior beyond cheap filesystem reads (symlink targets); heavy work lives in
services.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from odoo_cli.core.odoo_conf import OdooConf

#: Workspace-internal directories; never worktrees, and reserved as names.
INTERNAL_DIRS = (".repositories", ".venvs", ".run", ".data")


@dataclass
class Workspace:
    """A resolved workspace root, identified by `.repositories/odoo.git`."""

    root: Path
    config: OdooConf

    @property
    def repositories_dir(self) -> Path:
        return self.root / ".repositories"

    @property
    def venvs_dir(self) -> Path:
        return self.root / ".venvs"

    @property
    def run_dir(self) -> Path:
        return self.root / ".run"


@dataclass
class RepositorySpec:
    """A repository derived from `.repositories/{name}.git`, not a registry.

    `url` is the bare repo's `origin` remote; None is allowed (manual/local
    setups) and operations that must fetch raise `RepositoryHasNoRemote`.
    """

    name: str
    path: Path
    url: str | None


@dataclass
class Worktree:
    """A top-level workspace directory containing an `odoo/` entry."""

    name: str
    path: Path

    @property
    def odoo_path(self) -> Path:
        return self.path / "odoo"

    @property
    def is_linked(self) -> bool:
        return self.odoo_path.is_symlink()

    @property
    def linked_from(self) -> str | None:
        """Source worktree name, read from the `odoo/` symlink target."""
        if not self.is_linked:
            return None
        # target is e.g. ../19.0/odoo -> source worktree is its parent name
        return Path(os.readlink(self.odoo_path)).parent.name


@dataclass
class Target:
    """Resolved command target: where a command operates."""

    workspace: Workspace
    worktree: Worktree
    database: str

    @property
    def test_database(self) -> str:
        return f"{self.database}-test"


@dataclass
class Ports:
    """Allocated ports for one server instance (one shared reservation pool)."""

    http: int
    gevent: int

    def all(self) -> tuple[int, int]:
        return (self.http, self.gevent)


@dataclass
class ServerInstance:
    """Runtime server identity for one (worktree, database) pair.

    v1: `data_dir` stays None (odoo-bin's default, shared location).
    """

    target: Target
    run_dir: Path
    data_dir: Path | None = None


@dataclass
class OdooBinCommand:
    """Structured odoo-bin invocation, built only by OdooBinService.

    `argv` must not contain secrets; `redacted_argv` is safe to display and
    to persist under `.run/`.
    """

    executable: Path
    argv: list[str]
    cwd: Path
    env: dict[str, str] = field(default_factory=dict)
    redacted_argv: list[str] = field(default_factory=list)
    purpose: str = ""
