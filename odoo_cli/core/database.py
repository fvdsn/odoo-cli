"""Database lifecycle.

Rule (specs/requirements.md): any command that needs an initialized database
calls `ensure_initialized` — a missing target database is created and
initialized empty (base only, no modules) before the command proceeds.
Installed modules are read from the database; there is no configured list.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from odoo_cli.core import external_deps, filestore
from odoo_cli.core.errors import DatabaseExists, DatabaseNotFound, PostgresError
from odoo_cli.core.models import Target, Workspace
from odoo_cli.core.odoo_bin import OdooBinService, run_streamed
from odoo_cli.core.odoo_conf import demo_enabled
from odoo_cli.core.postgres import PostgresService
from odoo_cli.core.repositories import validate_name
from odoo_cli.util.locks import file_lock
from odoo_cli.util.process import ProcessRunner


class DatabaseService:
    def __init__(
        self,
        postgres: PostgresService,
        odoo_bin: OdooBinService,
        runner: ProcessRunner,
        venvs=None,  # VenvService; optional so tests without one keep working
    ):
        self.postgres = postgres
        self.odoo_bin = odoo_bin
        self.runner = runner
        self.venvs = venvs

    def ensure_initialized(self, target: Target, *, python: Path) -> bool:
        """Create and initialize the target database empty when missing.
        Returns True when it had to be created or initialized.

        Existence alone is not initialization: a crash between createdb and
        odoo-bin's base install (the slowest first-run window) leaves an
        existing-but-empty database, which must be healed here — otherwise
        every later `start`/`shell` fails reading ir_module_module.

        Serialized per database: two concurrent commands racing this window
        would otherwise both run createdb/base-install; the loser waits and
        then sees an initialized database."""
        conf = target.workspace.config
        lock = target.workspace.run_dir / f".init-{target.database}.lock"
        with file_lock(lock):
            if not self.postgres.db_exists(conf, target.database):
                if self.odoo_bin.capabilities(target).native_db_init:
                    # reuse odoo's own creation+init (`db init`) when it
                    # exists; demo comes from the conf, as the polyfill's
                    # `-i base` run would read it
                    command = self.odoo_bin.db_create_init(
                        target, python=python, demo=demo_enabled(conf)
                    )
                    run_streamed(self.runner, command)
                    return True
                self.postgres.create_db(conf, target.database)
            elif self.is_initialized(target):
                return False
            # polyfill, also the healing path: a db left behind by a crash
            # between creation and base install exists but has no registry
            command = self.odoo_bin.db_init(target, python=python)
            run_streamed(self.runner, command)
            return True

    def is_initialized(self, target: Target) -> bool:
        """Whether the database holds an initialized Odoo registry. A failing
        query means no ir_module_module table: not initialized."""
        return self._initialized(target.workspace.config, target.database)

    def _initialized(self, conf, name: str) -> bool:
        try:
            rows = self.postgres.sql(
                conf,
                name,
                "SELECT 1 FROM ir_module_module "
                "WHERE name = 'base' AND state = 'installed'",
            )
        except PostgresError:
            return False
        return bool(rows)

    def seed_from(self, workspace: Workspace, source: str, target: str) -> bool:
        """Copy database `source` to `target` (filestore included) as the
        starting point for a new worktree, so the source's installed modules
        need no reinstall. Returns True when the copy happened.

        A no-op when `target` already exists, or when `source` is missing or
        holds no initialized registry (an empty leftover seeds nothing useful;
        the empty-on-first-start rule applies instead). `createdb -T` needs
        the source free of sessions, so open connections on it are terminated
        (same policy as `db clone`)."""
        conf = workspace.config
        validate_name(target, kind="database name")
        if self.postgres.db_exists(conf, target):
            return False
        if not self.postgres.db_exists(conf, source):
            return False
        if not self._initialized(conf, source):
            return False
        self.postgres.copy_db(conf, source, target)
        self._sync_filestore(conf, source, target, shutil.copytree)
        return True

    def reset(self, target: Target, *, python: Path) -> list[str]:
        """Drop and recreate the database, reinstalling the module set read
        from it beforehand. A database that never had modules (or does not
        exist, or was left uninitialized by an interrupted init) is recreated
        empty. v1 does not touch the shared data_dir/filestore. Returns the
        reinstalled modules."""
        conf = target.workspace.config
        modules = self.resettable_modules(target)
        # deps first: failing here keeps the database intact instead of
        # leaving it dropped-and-empty after a failed reinstall
        if modules and self.venvs is not None:
            venv = self.venvs.ensure(target.workspace, target.worktree)
            external_deps.ensure_module_deps(
                self.venvs, self.runner, target.worktree, modules,
                venv.path, self.venvs.python_path(venv.path),
            )
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

    def drop(self, workspace: Workspace, name: str) -> bool:
        """Drop database `name` and its filestore. True when the db existed."""
        conf = workspace.config
        if not self.postgres.db_exists(conf, name):
            return False
        self.postgres.drop_db(conf, name)
        store = filestore.filestore_path(conf, name)
        if store.is_dir():
            shutil.rmtree(store)
        return True

    def installed_modules(self, target: Target) -> list[str]:
        """The set `db reset` reinstalls; the database is the source of truth."""
        return self.installed_modules_in(target.workspace.config, target.database)

    def installed_modules_in(self, conf, database: str) -> list[str]:
        rows = self.postgres.sql(
            conf,
            database,
            "SELECT name FROM ir_module_module WHERE state = 'installed'",
        )
        return sorted(rows)

    def list_databases(self, workspace: Workspace) -> list[dict]:
        """Every user database with its size, owner, Odoo version (None for a
        non-Odoo database) and filestore path (None when absent)."""
        conf = workspace.config
        entries = []
        for name, size, owner in self.postgres.list_dbs(conf):
            store = filestore.filestore_path(conf, name)
            entries.append(
                {
                    "name": name,
                    "size_bytes": size,
                    "owner": owner,
                    "version": self._base_version(conf, name),
                    "filestore": str(store) if store.is_dir() else None,
                }
            )
        return entries

    def clone(self, workspace: Workspace, source: str, target: str) -> bool:
        """Copy database `source` to `target`, filestore included.
        Returns True when a filestore was copied."""
        conf = workspace.config
        self._check_pair(conf, source, target)
        self.postgres.copy_db(conf, source, target)
        return self._sync_filestore(conf, source, target, shutil.copytree)

    def rename(self, workspace: Workspace, old: str, new: str) -> bool:
        """Rename database `old` to `new`, moving its filestore along.
        Returns True when a filestore was moved."""
        conf = workspace.config
        self._check_pair(conf, old, new)
        self.postgres.rename_db(conf, old, new)
        return self._sync_filestore(conf, old, new, shutil.move)

    def _check_pair(self, conf, source: str, target: str) -> None:
        validate_name(target, kind="database name")
        if not self.postgres.db_exists(conf, source):
            raise DatabaseNotFound(f"database '{source}' does not exist")
        if self.postgres.db_exists(conf, target):
            raise DatabaseExists(f"database '{target}' already exists")

    def _sync_filestore(self, conf, source: str, target: str, transfer) -> bool:
        src = filestore.filestore_path(conf, source)
        if not src.is_dir():
            return False
        dst = filestore.filestore_path(conf, target)
        if dst.is_dir():
            # no database of that name existed (checked above), so this
            # filestore is an orphan of a past drop; replace it
            shutil.rmtree(dst)
        transfer(src, dst)
        return True

    def _base_version(self, conf, name: str) -> str | None:
        try:
            rows = self.postgres.sql(
                conf,
                name,
                "SELECT latest_version FROM ir_module_module WHERE name = 'base'",
            )
        except PostgresError:
            return None
        return rows[0] if rows else None

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
