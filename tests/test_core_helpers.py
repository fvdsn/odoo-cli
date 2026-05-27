import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from odoo_cli.config import load_config, save_config
from odoo_cli.odoo import configured_addons_paths
from odoo_cli.postgres import terminate_connections


class ConfigTests(unittest.TestCase):
    def test_round_trips_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            config = {"postgres": {"db_name": "odoo-dev"}, "version": "master"}

            save_config(directory, config)

            self.assertEqual(load_config(directory), config)


class OdooPathTests(unittest.TestCase):
    def test_configured_addons_paths_skip_documentation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            config = {
                "repositories": {
                    "enterprise": True,
                    "documentation": True,
                    "themes": True,
                    "extra_addons": ["git@example.com:team/custom-addons.git"],
                }
            }

            paths = configured_addons_paths(directory, config, only_existing=False)

            self.assertEqual(
                paths,
                [
                    directory / "odoo" / "addons",
                    directory / "enterprise",
                    directory / "themes",
                    directory / "addons" / "custom-addons",
                ],
            )


class PostgresTests(unittest.TestCase):
    def test_terminate_connections_uses_psql_variable_for_db_name(self) -> None:
        with patch("odoo_cli.postgres.subprocess.run") as run:
            terminate_connections(
                {
                    "postgres": {
                        "host": False,
                        "port": False,
                        "user": False,
                        "password": False,
                    }
                },
                "demo'db",
            )

        cmd = run.call_args.args[0]
        self.assertIn("-v", cmd)
        self.assertIn("db_name=demo'db", cmd)
        self.assertIn("WHERE datname = :'db_name'", " ".join(cmd))


if __name__ == "__main__":
    unittest.main()
