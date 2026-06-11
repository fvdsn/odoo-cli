import tempfile
import unittest
from pathlib import Path

from odoo_cli.cli._click import testing
from odoo_cli.cli.context import CliContext, Services
from odoo_cli.cli.main import cli
from odoo_cli.core.venvs import READY_MARKER
from tests.fixtures.process import FakeProcessRunner
from tests.fixtures.workspace import make_env, make_workspace, make_worktree


class TestShellCommandsTestCase(unittest.TestCase):
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
        self.runner.expect("psql", stdout="1\n")
        self.runner.expect(self.python, stdout="")

    def invoke(self, *args):
        services = Services(process=self.runner, env=self.env)
        return self.cli_runner.invoke(cli, list(args), obj=CliContext(services=services))


class TestTestCommand(TestShellCommandsTestCase):
    def test_module_tests_use_test_database(self):
        result = self.invoke("test", "crm")
        self.assertEqual(result.exit_code, 0, result.output)
        argv = self.runner.stream_calls[0]
        self.assertIn("19.0-test", argv)
        self.assertIn("crm", argv[argv.index("-i") + 1])
        self.assertIn("--test-enable", argv)
        self.assertIn("tests passed", result.output)

    def test_creates_missing_test_database(self):
        self.runner.expect(
            "psql", "--no-psqlrc", "-tAc",
            "SELECT 1 FROM pg_database WHERE datname = '19.0-test'",
            stdout="",
        )
        self.runner.expect("createdb", stdout="")
        result = self.invoke("test", "crm")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn(("createdb", "19.0-test"), self.runner.calls)

    def test_installed_spec_reads_database(self):
        self.runner.expect(
            "psql", "--no-psqlrc", "-tAc",
            "SELECT name FROM ir_module_module WHERE state = 'installed'",
            stdout="base\ncrm\nsale\n",
        )
        result = self.invoke("test", "installed")
        self.assertEqual(result.exit_code, 0, result.output)
        argv = self.runner.stream_calls[0]
        self.assertEqual(argv[argv.index("-i") + 1], "crm,sale")

    def test_all_spec_enumerates_addons(self):
        addons = self.root / "19.0" / "odoo" / "addons"
        for module in ("crm", "sale"):
            (addons / module).mkdir(parents=True)
            (addons / module / "__manifest__.py").write_text("{}\n")
        (addons / "not_a_module").mkdir()
        result = self.invoke("test", "all")
        self.assertEqual(result.exit_code, 0, result.output)
        argv = self.runner.stream_calls[0]
        self.assertEqual(argv[argv.index("-i") + 1], "crm,sale")

    def test_all_spec_with_no_addons_is_an_error(self):
        result = self.invoke("test", "all")
        self.assertEqual(result.exit_code, 1)

    def test_tag_option(self):
        result = self.invoke("test", "crm", "-t", "test_lead")
        self.assertEqual(result.exit_code, 0, result.output)
        argv = self.runner.stream_calls[0]
        self.assertEqual(argv[argv.index("--test-tags") + 1], ".test_lead")

    def test_failure_exit_code(self):
        self.runner.stream_returncode = 1
        result = self.invoke("test", "crm")
        self.assertEqual(result.exit_code, 1)


class TestShellCommand(TestShellCommandsTestCase):
    def test_interactive_streams(self):
        result = self.invoke("shell")
        self.assertEqual(result.exit_code, 0, result.output)
        argv = self.runner.stream_calls[0]
        self.assertIn("shell", argv)
        self.assertIn("--no-http", argv)

    def test_code_execution_prints_output(self):
        self.runner.expect(self.python, stdout="42\n")
        result = self.invoke("shell", "-c", "print(6*7)")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("42", result.output)
        self.assertEqual(self.runner.stream_calls, [])  # not interactive
