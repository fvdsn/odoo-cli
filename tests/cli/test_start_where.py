import json
import tempfile
import unittest
from pathlib import Path

from odoo_cli.cli._click import testing
from odoo_cli.cli.context import CliContext, Services
from odoo_cli.cli.main import cli
from odoo_cli.core.server import RunStateStore, ServerService
from odoo_cli.core.venvs import READY_MARKER
from tests.fixtures.process import FakeProcessRunner
from tests.fixtures.workspace import make_env, make_worktree, make_workspace


class CommandTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name).resolve()
        self.env = make_env(self.home)
        self.root = make_workspace(self.home)
        make_worktree(self.root, "19.0", version="19.0")
        self.runner = FakeProcessRunner()
        self.cli_runner = testing.CliRunner()
        self.venv = self.root / ".venvs" / "19.0"
        (self.venv / "bin").mkdir(parents=True)
        (self.venv / "bin" / "python").write_text("")
        (self.venv / READY_MARKER).touch()

    def context(self) -> CliContext:
        services = Services(process=self.runner, env=self.env)
        services.server = ServerService(
            RunStateStore(), self.runner, port_free=lambda p: True
        )
        return CliContext(services=services)

    def invoke(self, *args):
        return self.cli_runner.invoke(cli, list(args), obj=self.context())


class TestStart(CommandTestCase):
    def script(self, db_exists=True, apps="crm\n"):
        self.runner.expect("psql", stdout="1\n" if db_exists else "")
        self.runner.expect("createdb", stdout="")
        self.runner.expect(
            "psql", "--no-psqlrc", "-tAc",
            "SELECT name FROM ir_module_module "
            "WHERE state = 'installed' AND application",
            stdout=apps,
        )
        self.runner.expect(str(self.venv / "bin" / "python"), stdout="")

    def test_start_streams_server_and_reserves_ports(self):
        self.script()
        result = self.invoke("start")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("http://localhost:8069", result.output)
        ports_file = self.root / ".run" / "19.0" / "19.0" / "ports"
        self.assertEqual(ports_file.read_text(), "http=8069\ngevent=8072\n")
        argv = self.runner.stream_calls[0]
        self.assertIn("--http-port", argv)
        self.assertIn("8069", argv)
        self.assertIn("-d", argv)
        self.assertIn("19.0", argv)

    def test_start_initializes_missing_database(self):
        self.script(db_exists=False, apps="")
        result = self.invoke("start")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Initialized empty database", result.output)
        self.assertIn(("createdb", "19.0"), self.runner.calls)
        init_run = next(
            c for c in self.runner.calls
            if c[0] == str(self.venv / "bin" / "python")
        )
        self.assertIn("--stop-after-init", init_run)

    def test_start_hints_when_no_app_installed(self):
        self.script(apps="")
        result = self.invoke("start")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("odoo module install", result.output)

    def test_explicit_db(self):
        self.script()
        result = self.invoke("start", "-d", "customer-a")
        self.assertEqual(result.exit_code, 0, result.output)
        ports_file = self.root / ".run" / "19.0" / "customer-a" / "ports"
        self.assertTrue(ports_file.is_file())


class TestWhere(CommandTestCase):
    def test_human_output(self):
        result = self.invoke("where")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn(f"workspace:   {self.root}", result.output)
        self.assertIn("worktree:    19.0", result.output)
        self.assertIn("version:     19.0", result.output)
        self.assertIn("allocated on first start", result.output)
        self.assertIn("odoo-bin", result.output)

    def test_json_output(self):
        result = self.invoke("where", "--json")
        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(data["worktree"], "19.0")
        self.assertEqual(data["database"], "19.0")
        self.assertEqual(data["ports"], {"http": 8069, "gevent": 8072, "reserved": False})
        self.assertIn("-c", data["command"])
        self.assertIn("--addons-path", data["command"])
        self.assertIsNone(data["linked_from"])

    def test_reserved_ports_shown(self):
        ports_file = self.root / ".run" / "19.0" / "19.0" / "ports"
        ports_file.parent.mkdir(parents=True)
        ports_file.write_text("http=8090\ngevent=8093\n")
        result = self.invoke("where", "--json")
        data = json.loads(result.output)
        self.assertEqual(data["ports"]["http"], 8090)
        self.assertTrue(data["ports"]["reserved"])

    def test_linked_worktree(self):
        make_worktree(self.root, "customer-a", linked_from="19.0")
        result = self.invoke("where", "-w", "customer-a", "--json")
        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(data["linked_from"], "19.0")
        self.assertEqual(data["database"], "customer-a")
