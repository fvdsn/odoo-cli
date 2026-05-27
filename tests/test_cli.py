import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from odoo_cli.config import save_config
from odoo_cli.main import app


def minimal_workspace_config() -> dict:
    return {
        "version": "master",
        "repositories": {
            "enterprise": False,
            "documentation": False,
            "themes": False,
            "extra_addons": [],
        },
        "postgres": {
            "host": False,
            "port": False,
            "user": False,
            "password": False,
            "db_name": "odoo-dev",
        },
        "odoo": {
            "http_port": 8069,
            "websocket_port": 8072,
            "data_dir": "~/.local/share/Odoo",
            "demo_data": True,
            "dev_mode": False,
            "install_modules": [],
        },
    }


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()

    def test_info_finds_workspace_from_nested_directory(self) -> None:
        cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "odoo" / "addons" / "sale"
            nested.mkdir(parents=True)
            save_config(root, minimal_workspace_config())
            try:
                os.chdir(nested)
                with patch("odoo_cli.commands.info.pid_for_port", return_value=None):
                    result = self.runner.invoke(app, ["info"])
            finally:
                os.chdir(cwd)

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Database: odoo-dev", result.output)
        self.assertIn("odoo: unknown", result.output)

    def test_info_errors_outside_workspace(self) -> None:
        cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                result = self.runner.invoke(app, ["info"])
            finally:
                os.chdir(cwd)

        self.assertEqual(result.exit_code, 1)
        self.assertIn("No config.toml found", result.output)

    def test_shell_exposes_command_option(self) -> None:
        result = self.runner.invoke(app, ["shell", "--help"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("--command", result.output)
        self.assertIn("-c", result.output)

    def test_run_is_not_a_top_level_command(self) -> None:
        result = self.runner.invoke(app, ["run", "print(1)"])

        self.assertNotEqual(result.exit_code, 0)


if __name__ == "__main__":
    unittest.main()
