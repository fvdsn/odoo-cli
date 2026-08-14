import tempfile
import unittest
from pathlib import Path

from odoo_cli.cli._click import testing
from odoo_cli.cli.context import CliContext, Services
from odoo_cli.cli.main import cli
from odoo_cli.core.venvs import READY_MARKER
from tests.fixtures.process import (
    FakeProcessRunner,
    createdb_from_template,
)
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
        # data_dir under the temp home: the test-db recreation removes the
        # test filestore and must never look at the real one
        conf = self.home / ".config" / "odoo" / "odoo.conf"
        conf.parent.mkdir(parents=True)
        conf.write_text(f"[options]\ndata_dir = {self.home / 'odoo-data'}\n")
        self.runner.expect("psql", stdout="1\n")
        self.runner.expect("dropdb", stdout="")
        self.runner.expect("createdb", stdout="")
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
        # the leftover test db (broad psql: exists) was recreated, so the
        # run starts from a schema matching exactly the modules it loads
        self.assertIn(("dropdb", "19.0-test"), self.runner.calls)
        self.assertIn(createdb_from_template("19.0-test"), self.runner.calls)

    def test_creates_missing_test_database(self):
        self.runner.expect(
            "psql", "--no-psqlrc", "-tAc",
            "SELECT 1 FROM pg_database WHERE datname = '19.0-test'",
            stdout="",
        )
        self.runner.expect("createdb", stdout="")
        result = self.invoke("test", "crm")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn(createdb_from_template("19.0-test"), self.runner.calls)

    def test_keep_db_rerun_updates_modules_in_test_db(self):
        # the installed-modules expectation matches both the target db and
        # the kept test db: everything is already in the test db, so the
        # rerun must go through -u — with -i odoo-bin would install nothing
        # and run 0 tests (the second `odoo test installed` regression)
        self.runner.expect(
            "psql", "--no-psqlrc", "-tAc",
            "SELECT name FROM ir_module_module WHERE state = 'installed'",
            stdout="base\ncrm\nsale\n",
        )
        result = self.invoke("test", "installed", "--keep-db")
        self.assertEqual(result.exit_code, 0, result.output)
        argv = self.runner.stream_calls[0]
        self.assertFalse(any(c[0] == "dropdb" for c in self.runner.calls))
        # kept modules are fully installed already: only their post_install
        # tests run correctly there — runbot's own batch pattern, a plain
        # registry load with neither -i nor -u (no upgrade of the kept db)
        self.assertNotIn("-i", argv)
        self.assertNotIn("-u", argv)
        self.assertEqual(
            argv[argv.index("--test-tags") + 1], "-at_install,/crm,/sale"
        )
        self.assertNotIn("--test-enable", argv)  # --test-tags enables tests

    def test_keep_db_fresh_modules_keep_both_phases(self):
        # a module absent from the kept db installs at its graph position,
        # so its at_install tests remain valid and are selected explicitly
        self.runner.expect(
            "psql", "--no-psqlrc", "-tAc",
            "SELECT name FROM ir_module_module WHERE state = 'installed'",
            stdout="base\ncrm\n",
        )
        result = self.invoke("test", "crm,stock", "--keep-db")
        self.assertEqual(result.exit_code, 0, result.output)
        argv = self.runner.stream_calls[0]
        self.assertEqual(argv[argv.index("-i") + 1], "stock")
        self.assertEqual(argv[argv.index("-u") + 1], "crm")
        self.assertEqual(
            argv[argv.index("--test-tags") + 1], "post_install,at_install/stock"
        )

    def test_keep_db_explicit_tags_override_phase_filter(self):
        self.runner.expect(
            "psql", "--no-psqlrc", "-tAc",
            "SELECT name FROM ir_module_module WHERE state = 'installed'",
            stdout="base\ncrm\n",
        )
        result = self.invoke("test", "crm", "--keep-db", "-t", "test_lead")
        self.assertEqual(result.exit_code, 0, result.output)
        argv = self.runner.stream_calls[0]
        self.assertEqual(argv[argv.index("--test-tags") + 1], ".test_lead")

    def test_installed_spec_installs_into_fresh_test_db(self):
        self.runner.expect(
            "psql", "--no-psqlrc", "-tAc",
            "SELECT name FROM ir_module_module WHERE state = 'installed'",
            stdout="base\ncrm\nsale\n",
        )
        result = self.invoke("test", "installed")
        self.assertEqual(result.exit_code, 0, result.output)
        argv = self.runner.stream_calls[0]
        self.assertEqual(argv[argv.index("-i") + 1], "crm,sale")
        self.assertNotIn("-u", argv)

    def test_installed_spec_initializes_missing_database(self):
        # right after `odoo init` the target database may not exist yet;
        # `test installed` ensures it like every database-reading command
        self.runner.expect(
            "psql", "--no-psqlrc", "-tAc",
            "SELECT 1 FROM pg_database WHERE datname = '19.0'",
            stdout="",
        )
        self.runner.expect(
            "psql", "--no-psqlrc", "-tAc",
            "SELECT name FROM ir_module_module WHERE state = 'installed'",
            stdout="base\n",
        )
        result = self.invoke("test", "installed")
        self.assertEqual(result.exit_code, 0, result.output)
        # 19+: creation and init are odoo-bin's own `db init` in one run
        init_run = self.runner.stream_calls[0]
        self.assertIn("init", init_run)
        self.assertEqual(init_run[init_run.index("init") + 1], "19.0")

    def test_all_spec_was_removed(self):
        result = self.invoke("test", "all")
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(self.runner.stream_calls, [])  # nothing ran

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
