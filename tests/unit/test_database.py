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


class TestEnsureInitialized(DatabaseTestCase):
    def test_creates_missing_database(self):
        self.db_exists(False)
        self.runner.expect("createdb", stdout="")
        self.runner.expect(str(self.python), stdout="")
        created = self.service.ensure_initialized(self.target, python=self.python)
        self.assertTrue(created)
        self.assertIn(("createdb", "19.0"), self.runner.calls)
        init_call = self.runner.calls[-1]
        self.assertIn("--stop-after-init", init_call)
        self.assertIn("--no-http", init_call)
        # "empty" means base only; without -i odoo-bin would not initialize
        self.assertEqual(init_call[init_call.index("-i") + 1], "base")

    def test_existing_database_untouched(self):
        self.db_exists(True)
        created = self.service.ensure_initialized(self.target, python=self.python)
        self.assertFalse(created)
        self.assertEqual(len(self.runner.calls), 1)  # only the existence check


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
        self.runner.expect(str(self.python), stdout="")
        reinstalled = self.service.reset(self.target, python=self.python)
        self.assertEqual(reinstalled, ["crm", "sale"])  # base excluded
        flat = [" ".join(c) for c in self.runner.calls]
        self.assertTrue(any("dropdb" in c for c in flat))
        install = self.runner.calls[-1]
        self.assertIn("-i", install)
        self.assertIn("crm,sale", install)

    def test_empty_database_stays_empty(self):
        self.runner.expect("psql", stdout="1\n")
        self.runner.expect("psql", "--no-psqlrc", "-tAc", MODULES_SQL,
                           stdout="base\n")
        self.runner.expect("dropdb", stdout="", effect=self._drop_effect)
        self.runner.expect("createdb", stdout="")
        self.runner.expect(str(self.python), stdout="")
        reinstalled = self.service.reset(self.target, python=self.python)
        self.assertEqual(reinstalled, [])
        init_calls = [c for c in self.runner.calls if c[0] == str(self.python)]
        self.assertEqual(len(init_calls), 1)  # init only, no reinstall run

    def test_missing_database_recreated_empty(self):
        self.db_exists(False)
        self.runner.expect("createdb", stdout="")
        self.runner.expect(str(self.python), stdout="")
        # second exists check inside ensure_initialized
        reinstalled = self.service.reset(self.target, python=self.python)
        self.assertEqual(reinstalled, [])
        self.assertFalse(any(c[0] == "dropdb" for c in self.runner.calls))
