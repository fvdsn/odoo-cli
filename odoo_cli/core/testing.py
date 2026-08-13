"""`odoo test` orchestration.

The test database is `{database}-test`, derived by convention and never
stored. It is recreated from scratch on every run (odoo-bin initializes it
together with the installed test modules; -i implies init on a fresh db):
at_install tests run per module during loading, with a registry of only the
modules loaded so far, so a test db carrying the schema of a previous run
breaks them (NOT NULL columns of not-yet-loaded modules). `--keep-db` opts
into reuse for fast reruns.
"""

from __future__ import annotations

from pathlib import Path

from odoo_cli.core import external_deps
from odoo_cli.core.database import DatabaseService
from odoo_cli.core.errors import OdooCliError, PostgresError
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

    def run(
        self,
        target: Target,
        module_spec: str,
        tags: list[str],
        *,
        keep_db: bool = False,
    ) -> None:
        """`module_spec`: a module name (comma-separable) or `installed`
        (modules installed in the target database)."""
        venv = self.venvs.ensure(target.workspace, target.worktree)
        python = self.venvs.python_path(venv.path)

        modules = self._resolve_modules(target, module_spec, python=python)
        external_deps.ensure_module_deps(
            self.venvs, self.runner, target.worktree, modules, venv.path, python
        )
        conf = target.workspace.config
        present: set[str] = set()
        exists = self.database.postgres.db_exists(conf, target.test_database)
        if exists and not keep_db:
            # a leftover test db carries the schema of everything a previous
            # run installed; tests of early-graph modules would then insert
            # into tables holding NOT NULL columns of not-yet-loaded modules
            self.database.drop(target.workspace, target.test_database)
            exists = False
        if not exists:
            self.database.postgres.create_db(conf, target.test_database)
        else:
            present = set(self._test_db_modules(target))

        # odoo-bin runs tests only for modules it installs or updates in this
        # very run: with --keep-db, modules already in the test db go through
        # -u so their tests run again (-i would skip them and run 0 tests)
        install = [m for m in modules if m not in present]
        update = [m for m in modules if m in present]
        command = self.odoo_bin.tests(target, install, update, tags, python=python)
        run_streamed(self.runner, command)

    def _test_db_modules(self, target: Target) -> list[str]:
        """Modules already installed in the reused test database; [] for a
        leftover empty/uninitialized one (odoo-bin's -i then initializes it)."""
        try:
            return self.database.installed_modules_in(
                target.workspace.config, target.test_database
            )
        except PostgresError:
            return []

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
