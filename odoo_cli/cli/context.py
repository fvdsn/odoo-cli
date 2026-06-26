"""CLI context: the service container handed to command adapters."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import cached_property

from odoo_cli.cli.output import Output
from odoo_cli.core.config_service import ConfigService
from odoo_cli.core.database import DatabaseService
from odoo_cli.core.modules import ModuleService
from odoo_cli.core.odoo_bin import OdooBinService
from odoo_cli.core.postgres import PostgresService
from odoo_cli.core.repositories import RepositoryService
from odoo_cli.core.server import RunStateStore, ServerService
from odoo_cli.core.shell import ShellService
from odoo_cli.core.sync import PullService
from odoo_cli.core.target import TargetResolver
from odoo_cli.core.testing import TestingService
from odoo_cli.core.venvs import VenvService
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
        return WorktreeService(self.git, self.repositories, self.postgres)

    @cached_property
    def pull(self) -> PullService:
        return PullService(self.git)

    @cached_property
    def venvs(self) -> VenvService:
        return VenvService(self.process)

    @cached_property
    def postgres(self) -> PostgresService:
        return PostgresService(self.process)

    @cached_property
    def odoo_bin(self) -> OdooBinService:
        return OdooBinService(self.env)

    @cached_property
    def database(self) -> DatabaseService:
        return DatabaseService(self.postgres, self.odoo_bin, self.process)

    @cached_property
    def server(self) -> ServerService:
        return ServerService(RunStateStore(), self.process)

    @cached_property
    def modules(self) -> ModuleService:
        return ModuleService(self.database, self.odoo_bin, self.venvs, self.process)

    @cached_property
    def testing(self) -> TestingService:
        return TestingService(self.database, self.odoo_bin, self.venvs, self.process)

    @cached_property
    def shell(self) -> ShellService:
        return ShellService(self.database, self.odoo_bin, self.venvs, self.process)

    @cached_property
    def config(self) -> ConfigService:
        return ConfigService(self.workspace, self.repositories)


@dataclass
class CliContext:
    services: Services = field(default_factory=Services)
    output: Output = field(default_factory=Output)
