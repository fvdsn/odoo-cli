"""Database lifecycle.

Rule (docs/requirements.md): any command that needs an initialized database
calls `ensure_initialized` — a missing target database is created and
initialized empty (base only, no modules) before the command proceeds.
Installed modules are read from the database; there is no configured list.
"""

from __future__ import annotations

from pathlib import Path

from odoo_cli.core.models import Target
from odoo_cli.core.odoo_bin import OdooBinService
from odoo_cli.core.postgres import PostgresService
from odoo_cli.util.process import ProcessRunner


class DatabaseService:
    def __init__(
        self,
        postgres: PostgresService,
        odoo_bin: OdooBinService,
        runner: ProcessRunner,
    ):
        self.postgres = postgres
        self.odoo_bin = odoo_bin
        self.runner = runner

    def ensure_initialized(self, target: Target, *, python: Path) -> bool:
        """Create and initialize the target database empty when missing.
        Returns True when it had to be created."""
        conf = target.workspace.config
        if self.postgres.db_exists(conf, target.database):
            return False
        self.postgres.create_db(conf, target.database)
        command = self.odoo_bin.db_init(target, python=python)
        self.runner.run(command.argv, cwd=command.cwd, extra_env=command.env)
        return True

    def reset(self, target: Target, *, python: Path) -> list[str]:
        """Drop and recreate the database, reinstalling the module set read
        from it beforehand. A database that never had modules (or does not
        exist) is recreated empty. v1 does not touch the shared data_dir/
        filestore. Returns the reinstalled modules."""
        conf = target.workspace.config
        modules: list[str] = []
        if self.postgres.db_exists(conf, target.database):
            modules = [
                m for m in self.installed_modules(target) if m != "base"
            ]
            self.postgres.drop_db(conf, target.database)
        self.ensure_initialized(target, python=python)
        if modules:
            command = self.odoo_bin.module_install(target, modules, python=python)
            self.runner.run(command.argv, cwd=command.cwd, extra_env=command.env)
        return modules

    def installed_modules(self, target: Target) -> list[str]:
        """The set `db reset` reinstalls; the database is the source of truth."""
        rows = self.postgres.sql(
            target.workspace.config,
            target.database,
            "SELECT name FROM ir_module_module WHERE state = 'installed'",
        )
        return sorted(rows)

    def installed_applications(self, target: Target) -> list[str]:
        """Installed apps (not auto-installed technical modules); used for the
        `odoo start` hint pointing at `odoo module install`."""
        rows = self.postgres.sql(
            target.workspace.config,
            target.database,
            "SELECT name FROM ir_module_module "
            "WHERE state = 'installed' AND application",
        )
        return sorted(rows)
