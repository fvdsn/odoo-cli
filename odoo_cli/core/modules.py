"""Module install/update orchestration.

This is the only way modules get installed; there is no configured module
list anywhere. The target database is created on demand first, so
`odoo module install crm` works right after `odoo init`.
"""

from __future__ import annotations

from odoo_cli.core.database import DatabaseService
from odoo_cli.core.models import Target
from odoo_cli.core.odoo_bin import OdooBinService, run_streamed
from odoo_cli.core.venvs import VenvService
from odoo_cli.util.process import ProcessRunner


class ModuleService:
    def __init__(
        self,
        database: DatabaseService,
        odoo_bin: OdooBinService,
        venvs: VenvService,
        runner: ProcessRunner,
    ):
        self.database = database
        self.odoo_bin = odoo_bin
        self.venvs = venvs
        self.runner = runner

    def install(self, target: Target, modules: list[str]) -> None:
        python = self._python(target)
        self.database.ensure_initialized(target, python=python)
        command = self.odoo_bin.module_install(target, modules, python=python)
        run_streamed(self.runner, command)

    def update(self, target: Target, modules: list[str] | None) -> None:
        """Update modules (None: all installed). Runs whether the server is
        running or not; it never stops a running server."""
        python = self._python(target)
        self.database.ensure_initialized(target, python=python)
        command = self.odoo_bin.module_update(target, modules, python=python)
        run_streamed(self.runner, command)

    def _python(self, target: Target):
        venv = self.venvs.ensure(target.workspace, target.worktree)
        return self.venvs.python_path(venv.path)
