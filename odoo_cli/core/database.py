"""Database lifecycle.

Rule (docs/requirements.md): any command that needs an initialized database
calls `ensure_initialized` — a missing target database is created and
initialized empty (base only, no modules) before the command proceeds.
Installed modules are read from the database; there is no configured list.
"""

from __future__ import annotations

from pathlib import Path

from odoo_cli.core.errors import PostgresError
from odoo_cli.core.models import Target
from odoo_cli.core.odoo_bin import OdooBinService, run_streamed
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
        Returns True when it had to be created or initialized.

        Existence alone is not initialization: a crash between createdb and
        odoo-bin's base install (the slowest first-run window) leaves an
        existing-but-empty database, which must be healed here — otherwise
        every later `start`/`shell` fails reading ir_module_module."""
        conf = target.workspace.config
        if not self.postgres.db_exists(conf, target.database):
            self.postgres.create_db(conf, target.database)
        elif self.is_initialized(target):
            return False
        command = self.odoo_bin.db_init(target, python=python)
        run_streamed(self.runner, command)
        return True

    def is_initialized(self, target: Target) -> bool:
        """Whether the database holds an initialized Odoo registry. A failing
        query means no ir_module_module table: not initialized."""
        try:
            rows = self.postgres.sql(
                target.workspace.config,
                target.database,
                "SELECT 1 FROM ir_module_module "
                "WHERE name = 'base' AND state = 'installed'",
            )
        except PostgresError:
            return False
        return bool(rows)

    def reset(self, target: Target, *, python: Path) -> list[str]:
        """Drop and recreate the database, reinstalling the module set read
        from it beforehand. A database that never had modules (or does not
        exist, or was left uninitialized by an interrupted init) is recreated
        empty. v1 does not touch the shared data_dir/filestore. Returns the
        reinstalled modules."""
        conf = target.workspace.config
        modules = self.resettable_modules(target)
        if self.postgres.db_exists(conf, target.database):
            self.postgres.drop_db(conf, target.database)
        self.ensure_initialized(target, python=python)
        if modules:
            command = self.odoo_bin.module_install(target, modules, python=python)
            run_streamed(self.runner, command)
        return modules

    def resettable_modules(self, target: Target) -> list[str]:
        """The non-base modules a reset would reinstall; [] for a missing or
        uninitialized database. Lets `db reset` show the set before dropping,
        so an interrupted reset does not silently lose it."""
        conf = target.workspace.config
        if not self.postgres.db_exists(conf, target.database):
            return []
        if not self.is_initialized(target):
            return []
        return [m for m in self.installed_modules(target) if m != "base"]

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
