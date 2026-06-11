"""The real ProcessRunner against tiny local commands (no network)."""

import sys
import unittest

from odoo_cli.util.process import ProcessError, ProcessRunner


class TestProcessRunner(unittest.TestCase):
    def setUp(self):
        self.runner = ProcessRunner()

    def test_run_captures_output(self):
        result = self.runner.run([sys.executable, "-c", "print('hello')"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "hello")

    def test_run_check_raises(self):
        with self.assertRaises(ProcessError) as cm:
            self.runner.run([sys.executable, "-c", "raise SystemExit(3)"])
        self.assertEqual(cm.exception.result.returncode, 3)

    def test_run_no_check_returns_result(self):
        result = self.runner.run(
            [sys.executable, "-c", "raise SystemExit(3)"], check=False
        )
        self.assertEqual(result.returncode, 3)

    def test_extra_env_is_merged(self):
        result = self.runner.run(
            [sys.executable, "-c", "import os; print(os.environ['ODOO_CLI_X'])"],
            extra_env={"ODOO_CLI_X": "1"},
        )
        self.assertEqual(result.stdout.strip(), "1")
