import tempfile
import unittest
from pathlib import Path

from odoo_cli.core.errors import PostgresError
from odoo_cli.core.odoo_conf import OdooConf
from odoo_cli.core.postgres import PostgresService
from tests.fixtures.process import FakeProcessRunner


class PostgresTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.conf = OdooConf.load(Path(self._tmp.name) / "odoo.conf")
        self.runner = FakeProcessRunner()
        self.service = PostgresService(self.runner, which=lambda n: None)


class TestEnv(PostgresTestCase):
    def test_false_values_are_not_exported(self):
        self.conf.set("db_host", "False")
        self.conf.set("db_user", "dev")
        self.conf.set("db_password", "hunter2")
        env = self.service.env(self.conf)
        self.assertEqual(env, {"PGUSER": "dev", "PGPASSWORD": "hunter2"})

    def test_password_via_env_not_argv(self):
        self.conf.set("db_password", "hunter2")
        self.runner.expect("psql", stdout="1\n")
        self.service.check_connection(self.conf)
        for call in self.runner.calls:
            self.assertNotIn("hunter2", " ".join(call))


class TestDatabases(PostgresTestCase):
    def test_db_exists(self):
        self.runner.expect("psql", stdout="1\n")
        self.assertTrue(self.service.db_exists(self.conf, "x"))
        self.runner.expect("psql", stdout="\n")
        self.assertFalse(self.service.db_exists(self.conf, "x"))

    def test_create_db_failure_is_typed(self):
        self.runner.expect("createdb", returncode=1, stderr="permission denied")
        with self.assertRaises(PostgresError) as cm:
            self.service.create_db(self.conf, "x")
        self.assertIn("permission denied", cm.exception.hint)

    def test_drop_terminates_connections_first(self):
        self.runner.expect("psql", stdout="")
        self.runner.expect("dropdb", stdout="")
        self.service.drop_db(self.conf, "x")
        self.assertIn("pg_terminate_backend", self.runner.calls[0][3])
        self.assertEqual(self.runner.calls[1][0], "dropdb")

    def test_sql_returns_rows(self):
        self.runner.expect("psql", stdout="crm\nsale\n\n")
        rows = self.service.sql(self.conf, "db", "SELECT name FROM x")
        self.assertEqual(rows, ["crm", "sale"])
