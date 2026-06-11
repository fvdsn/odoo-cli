"""CLI context: the service container handed to command adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from typing import Mapping

from odoo_cli.cli.output import Output
from odoo_cli.core.odoo_bin import OdooBinService
from odoo_cli.core.postgres import PostgresService
from odoo_cli.core.repositories import RepositoryService
from odoo_cli.core.venvs import VenvService
from odoo_cli.core.target import TargetResolver
from odoo_cli.core.workspace import WorkspaceResolver
from odoo_cli.core.worktrees import WorktreeService
from odoo_cli.util.git import Git
from odoo_cli.util.process import ProcessRunner


class Services:
    """Lazy container for core services.

    Constructed once per invocation; tests inject fakes by assigning
    attributes (cached_property allows plain assignment) or passing a fake
    process runner. Core services are added as cached properties when
    implemented.
    """

    def __init__(
        self,
        process: ProcessRunner | None = None,
        env: Mapping[str, str] | None = None,
    ):
        self.process = process or ProcessRunner()
        self.env = env  # None means os.environ; tests inject isolation

    @cached_property
    def workspace(self) -> WorkspaceResolver:
        return WorkspaceResolver(self.env)

    @cached_property
    def targets(self) -> TargetResolver:
        return TargetResolver(self.workspace, self.env)

    @cached_property
    def git(self) -> Git:
        return Git(self.process)

    @cached_property
    def repositories(self) -> RepositoryService:
        return RepositoryService(self.git)

    @cached_property
    def worktrees(self) -> WorktreeService:
        return WorktreeService(self.git, self.repositories)

    @cached_property
    def venvs(self) -> VenvService:
        return VenvService(self.process)

    @cached_property
    def postgres(self) -> PostgresService:
        return PostgresService(self.process)

    @cached_property
    def odoo_bin(self) -> OdooBinService:
        return OdooBinService(self.env)


@dataclass
class CliContext:
    services: Services = field(default_factory=Services)
    output: Output = field(default_factory=Output)
