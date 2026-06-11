import contextlib
import io
import unittest

from odoo_cli import __version__
from odoo_cli.cli._click import click, testing
from odoo_cli.cli.main import cli, main
from odoo_cli.core.errors import WorktreeNotFound


class TestCliGroup(unittest.TestCase):
    def setUp(self):
        self.runner = testing.CliRunner()

    def test_version(self):
        result = self.runner.invoke(cli, ["--version"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn(__version__, result.output)
        self.assertIn("odoo", result.output)

    def test_help(self):
        for flags in (["--help"], ["-h"]):
            result = self.runner.invoke(cli, flags)
            self.assertEqual(result.exit_code, 0)
            self.assertIn("Usage:", result.output)


class TestErrorTranslation(unittest.TestCase):
    def _register(self, name, callback):
        cli.add_command(click.command(name=name)(callback))
        self.addCleanup(cli.commands.pop, name)

    def _run(self, argv):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = main(argv)
        return code, stderr.getvalue()

    def test_usage_error_exits_2(self):
        code, stderr = self._run(["definitely-not-a-command"])
        self.assertEqual(code, 2)
        self.assertIn("definitely-not-a-command", stderr)

    def test_core_error_exits_1_with_hint(self):
        def boom():
            raise WorktreeNotFound(
                "no worktree named 'x'", hint="run `odoo worktree create x`"
            )

        self._register("boom", boom)
        code, stderr = self._run(["boom"])
        self.assertEqual(code, 1)
        self.assertIn("error: no worktree named 'x'", stderr)
        self.assertIn("odoo worktree create x", stderr)

    def test_success_exits_0(self):
        self._register("ok", lambda: None)
        code, _ = self._run(["ok"])
        self.assertEqual(code, 0)
