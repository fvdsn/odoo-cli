"""CLI context: the service container handed to command adapters."""

from __future__ import annotations

from dataclasses import dataclass, field

from odoo_cli.cli.output import Output
from odoo_cli.util.process import ProcessRunner


class Services:
    """Lazy container for core services.

    Constructed once per invocation; tests inject fakes by assigning
    attributes (or passing a fake process runner) before invoking commands.
    Core services are added here as cached properties when implemented.
    """

    def __init__(self, process: ProcessRunner | None = None):
        self.process = process or ProcessRunner()


@dataclass
class CliContext:
    services: Services = field(default_factory=Services)
    output: Output = field(default_factory=Output)
