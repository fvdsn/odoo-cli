"""`odoo test` orchestration.

The test database is `{database}-test`, derived by convention and never
stored. It is created on demand; odoo-bin initializes it together with the
installed test modules (-i implies init on a fresh db).
"""

from __future__ import annotations

from pathlib import Path

from odoo_cli.core import external_deps
from odoo_cli.core.database import DatabaseService
from odoo_cli.core.errors import OdooCliError
from odoo_cli.core.models import Target
from odoo_cli.core.odoo_bin import OdooBinService, run_streamed
from odoo_cli.core.venvs import VenvService
from odoo_cli.util.process import ProcessRunner


class TestingService:
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

    def run(self, target: Target, module_spec: str, tags: list[str]) -> None:
        """`module_spec`: a module name (comma-separable) or `installed`
        (modules installed in the target database)."""
        venv = self.venvs.ensure(target.workspace, target.worktree)
        python = self.venvs.python_path(venv.path)

        modules = self._resolve_modules(target, module_spec, python=python)
        external_deps.ensure_module_deps(
            self.venvs, self.runner, target.worktree, modules, venv.path, python
        )
        conf = target.workspace.config
        if not self.database.postgres.db_exists(conf, target.test_database):
            self.database.postgres.create_db(conf, target.test_database)

        command = self.odoo_bin.tests(target, modules, tags, python=python)
        run_streamed(self.runner, command)

    def _resolve_modules(
        self, target: Target, spec: str, *, python: Path
    ) -> list[str]:
        if spec == "installed":
            # `installed` reads the target database, so the usual rule
            # applies: a missing database is created and initialized first
            self.database.ensure_initialized(target, python=python)
            return [
                m for m in self.database.installed_modules(target) if m != "base"
            ] or ["base"]
        if spec == "all":
            # removed: installing every addon takes hours; nobody ran it
            raise OdooCliError(
                "`odoo test all` was removed",
                hint="name modules (`odoo test crm,sale`) or use `odoo test installed`",
            )
        return [m for m in spec.split(",") if m]
