import tempfile
import unittest
from pathlib import Path

from odoo_cli.cli._click import testing
from odoo_cli.cli.context import CliContext, Services
from odoo_cli.cli.main import cli
from odoo_cli.core.venvs import READY_MARKER
from tests.fixtures.process import FakeProcessRunner
from tests.fixtures.workspace import make_env, make_workspace, make_worktree


class ModuleCommandsTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name).resolve()
        self.env = make_env(self.home)
        self.root = make_workspace(self.home)
        make_worktree(self.root, "19.0", version="19.0")
        self.runner = FakeProcessRunner()
        self.cli_runner = testing.CliRunner()
        venv = self.root / ".venvs" / "19.0"
        (venv / "bin").mkdir(parents=True)
        (venv / "bin" / "python").write_text("")
        (venv / READY_MARKER).touch()
        self.python = str(venv / "bin" / "python")
        self.runner.expect("psql", stdout="1\n")  # db exists by default
        self.runner.expect(self.python, stdout="")

    def invoke(self, *args):
        services = Services(process=self.runner, env=self.env)
        return self.cli_runner.invoke(cli, list(args), obj=CliContext(services=services))


class TestModuleInstall(ModuleCommandsTestCase):
    def test_install_streams_polyfill(self):
        result = self.invoke("module", "install", "crm", "sale")
        self.assertEqual(result.exit_code, 0, result.output)
        argv = self.runner.stream_calls[0]
        self.assertIn("-i", argv)
        self.assertIn("crm,sale", argv)
        self.assertIn("--stop-after-init", argv)
        self.assertIn("installed crm, sale", result.output)

    def test_install_requires_modules(self):
        result = self.invoke("module", "install")
        self.assertEqual(result.exit_code, 2)

    def test_install_failure_is_an_error(self):
        self.runner.stream_returncode = 1
        result = self.invoke("module", "install", "crm")
        self.assertEqual(result.exit_code, 1)


class TestUpdate(ModuleCommandsTestCase):
    def test_update_defaults_to_all(self):
        result = self.invoke("update")
        self.assertEqual(result.exit_code, 0, result.output)
        argv = self.runner.stream_calls[0]
        self.assertIn("-u", argv)
        self.assertIn("all", argv)
        self.assertIn("updated all modules", result.output)

    def test_update_specific(self):
        result = self.invoke("update", "sale")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("sale", self.runner.stream_calls[0])


class TestDbReset(ModuleCommandsTestCase):
    def test_reset_reports_reinstalled_modules(self):
        self.runner.expect(
            "psql", "--no-psqlrc", "-tAc",
            "SELECT name FROM ir_module_module WHERE state = 'installed'",
            stdout="base\ncrm\n",
        )
        self.runner.expect(
            "dropdb", stdout="",
            effect=lambda call: self.runner.expect(
                "psql", "--no-psqlrc", "-tAc",
                "SELECT 1 FROM pg_database WHERE datname = '19.0'",
                stdout="",
            ),
        )
        self.runner.expect("createdb", stdout="")
        result = self.invoke("db", "reset")
        self.assertEqual(result.exit_code, 0, result.output)
        # the set is announced before the drop: an interrupted reset would
        # otherwise silently lose it
        self.assertIn("will reinstall after reset: crm", result.output)
        self.assertIn("reinstalled: crm", result.output)
