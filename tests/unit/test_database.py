import tempfile
import unittest
from pathlib import Path

from odoo_cli.core.database import DatabaseService
from odoo_cli.core.models import Target, Workspace, Worktree
from odoo_cli.core.odoo_bin import OdooBinService
from odoo_cli.core.odoo_conf import OdooConf
from odoo_cli.core.postgres import PostgresService
from tests.fixtures.process import FakeProcessRunner
from tests.fixtures.workspace import make_env, make_workspace, make_worktree

MODULES_SQL = "SELECT name FROM ir_module_module WHERE state = 'installed'"


class DatabaseTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)
        self.root = make_workspace(self.home)
        make_worktree(self.root, "19.0", version="19.0")
        conf = OdooConf.load(self.home / "odoo.conf")
        self.target = Target(
            workspace=Workspace(root=self.root, config=conf),
            worktree=Worktree(name="19.0", path=self.root / "19.0"),
            database="19.0",
        )
        self.runner = FakeProcessRunner()
        self.python = Path("/venv/bin/python")
        self.service = DatabaseService(
            PostgresService(self.runner, which=lambda n: None),
            OdooBinService(make_env(self.home)),
            self.runner,
        )

    def db_exists(self, exists: bool):
        self.runner.expect(
            "psql", "--no-psqlrc", "-tAc",
            "SELECT 1 FROM pg_database WHERE datname = '19.0'",
            stdout="1\n" if exists else "",
        )

    def base_installed(self, installed: bool | None):
        """None: the query itself fails (no ir_module_module table)."""
        self.runner.expect(
            "psql", "--no-psqlrc", "-tAc",
            "SELECT 1 FROM ir_module_module "
            "WHERE name = 'base' AND state = 'installed'",
            stdout="1\n" if installed else "",
            returncode=2 if installed is None else 0,
        )


class TestEnsureInitialized(DatabaseTestCase):
    def test_creates_missing_database(self):
        self.db_exists(False)
        self.runner.expect("createdb", stdout="")
        created = self.service.ensure_initialized(self.target, python=self.python)
        self.assertTrue(created)
        self.assertIn(("createdb", "19.0"), self.runner.calls)
        # the init run is streamed: its output goes to the terminal live
        init_call = self.runner.stream_calls[-1]
        self.assertIn("--stop-after-init", init_call)
        self.assertIn("--no-http", init_call)
        # "empty" means base only; without -i odoo-bin would not initialize
        self.assertEqual(init_call[init_call.index("-i") + 1], "base")

    def test_existing_database_untouched(self):
        self.db_exists(True)
        self.base_installed(True)
        created = self.service.ensure_initialized(self.target, python=self.python)
        self.assertFalse(created)
        self.assertEqual(len(self.runner.calls), 2)  # existence + init probes
        self.assertEqual(self.runner.stream_calls, [])

    def test_existing_uninitialized_database_is_healed(self):
        # crash between createdb and the base install: the db exists but
        # has no registry; every later command must converge, not loop
        self.db_exists(True)
        self.base_installed(None)  # query fails: no ir_module_module table
        created = self.service.ensure_initialized(self.target, python=self.python)
        self.assertTrue(created)
        init_call = self.runner.stream_calls[-1]
        self.assertEqual(init_call[init_call.index("-i") + 1], "base")
        self.assertFalse(any(c[0] == "createdb" for c in self.runner.calls))


class TestReset(DatabaseTestCase):
    def _drop_effect(self, call):
        # after dropdb, the database no longer exists
        self.db_exists(False)

    def test_reinstalls_module_set_from_database(self):
        self.runner.expect("psql", stdout="1\n")  # db_exists checks
        self.runner.expect("psql", "--no-psqlrc", "-tAc", MODULES_SQL,
                           stdout="base\ncrm\nsale\n")
        self.runner.expect("dropdb", stdout="", effect=self._drop_effect)
        self.runner.expect("createdb", stdout="")
        reinstalled = self.service.reset(self.target, python=self.python)
        self.assertEqual(reinstalled, ["crm", "sale"])  # base excluded
        flat = [" ".join(c) for c in self.runner.calls]
        self.assertTrue(any("dropdb" in c for c in flat))
        # init and reinstall are streamed so a long reinstall shows progress
        install = self.runner.stream_calls[-1]
        self.assertIn("-i", install)
        self.assertIn("crm,sale", install)

    def test_empty_database_stays_empty(self):
        self.runner.expect("psql", stdout="1\n")
        self.runner.expect("psql", "--no-psqlrc", "-tAc", MODULES_SQL,
                           stdout="base\n")
        self.runner.expect("dropdb", stdout="", effect=self._drop_effect)
        self.runner.expect("createdb", stdout="")
        reinstalled = self.service.reset(self.target, python=self.python)
        self.assertEqual(reinstalled, [])
        self.assertEqual(len(self.runner.stream_calls), 1)  # init, no reinstall

    def test_reset_of_uninitialized_database_recreates_empty(self):
        # `db reset` is the natural repair command and must work on a db
        # bricked by an interrupted init instead of failing on the query
        self.runner.expect("psql", stdout="")  # broad: terminate-backends etc.
        self.db_exists(True)
        self.base_installed(None)
        self.runner.expect("dropdb", stdout="", effect=self._drop_effect)
        self.runner.expect("createdb", stdout="")
        reinstalled = self.service.reset(self.target, python=self.python)
        self.assertEqual(reinstalled, [])
        self.assertEqual(len(self.runner.stream_calls), 1)  # fresh init only

    def test_missing_database_recreated_empty(self):
        self.db_exists(False)
        self.runner.expect("createdb", stdout="")
        # second exists check inside ensure_initialized
        reinstalled = self.service.reset(self.target, python=self.python)
        self.assertEqual(reinstalled, [])
        self.assertFalse(any(c[0] == "dropdb" for c in self.runner.calls))
