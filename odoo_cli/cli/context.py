"""CLI context: the service container handed to command adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property

from odoo_cli.cli.output import Output
from odoo_cli.core.workspace import WorkspaceResolver
from odoo_cli.util.process import ProcessRunner


class Services:
    """Lazy container for core services.

    Constructed once per invocation; tests inject fakes by assigning
    attributes (cached_property allows plain assignment) or passing a fake
    process runner. Core services are added as cached properties when
    implemented.
    """

    def __init__(self, process: ProcessRunner | None = None):
        self.process = process or ProcessRunner()

    @cached_property
    def workspace(self) -> WorkspaceResolver:
        return WorkspaceResolver()


@dataclass
class CliContext:
    services: Services = field(default_factory=Services)
    output: Output = field(default_factory=Output)
