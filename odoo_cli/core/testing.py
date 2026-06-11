"""`odoo test` orchestration.

The test database is `{database}-test`, derived by convention and never
stored. It is created on demand; odoo-bin initializes it together with the
installed test modules (-i implies init on a fresh db).
"""

from __future__ import annotations

from odoo_cli.core.database import DatabaseService
from odoo_cli.core.errors import ProcessFailed
from odoo_cli.core.models import Target
from odoo_cli.core.odoo_bin import OdooBinService
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
        """`module_spec`: a module name, `installed` (modules installed in
        the target database), or `all`."""
        venv = self.venvs.ensure(target.workspace, target.worktree)
        python = self.venvs.python_path(venv.path)

        modules = self._resolve_modules(target, module_spec)
        conf = target.workspace.config
        if not self.database.postgres.db_exists(conf, target.test_database):
            self.database.postgres.create_db(conf, target.test_database)

        command = self.odoo_bin.tests(target, modules, tags, python=python)
        code = self.runner.stream(
            command.argv, cwd=command.cwd, extra_env=command.env
        )
        if code != 0:
            raise ProcessFailed(
                f"tests failed (odoo-bin exited {code})",
                argv=command.redacted_argv,
                returncode=code,
            )

    def _resolve_modules(self, target: Target, spec: str) -> list[str]:
        if spec == "installed":
            return [
                m for m in self.database.installed_modules(target) if m != "base"
            ] or ["base"]
        if spec == "all":
            return ["all"]
        return [m for m in spec.split(",") if m]
