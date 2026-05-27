import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from odoo_cli.config import load_config, normalize_config, save_config
from odoo_cli.odoo import configured_addons_paths
from odoo_cli.postgres import terminate_connections
from odoo_cli.workspace import find_workspace_root


def minimal_workspace_config() -> dict:
    return {
        "repositories": {
            "enterprise": False,
            "documentation": False,
            "themes": False,
            "extra_addons": [],
        },
        "postgres": {"db_name": "odoo-dev"},
        "odoo": {},
    }


class ConfigTests(unittest.TestCase):
    def test_round_trips_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            config = {"postgres": {"db_name": "odoo-dev"}, "version": "master"}

            save_config(directory, config)

            self.assertEqual(load_config(directory), config)

    def test_normalizes_missing_workspace_defaults(self) -> None:
        config = normalize_config(minimal_workspace_config())

        self.assertEqual(config["version"], "master")
        self.assertEqual(config["postgres"]["host"], False)
        self.assertEqual(config["postgres"]["db_name"], "odoo-dev")
        self.assertEqual(config["odoo"]["http_port"], 8069)
        self.assertEqual(config["remotes"]["dev_url"], "git@github.com:odoo-dev/{repo}.git")

    def test_normalization_preserves_unknown_keys(self) -> None:
        config = normalize_config({"repositories": {}, "postgres": {}, "odoo": {}, "custom": 1})

        self.assertEqual(config["custom"], 1)

    def test_load_config_normalizes_workspace_configs_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            save_config(directory, minimal_workspace_config())

            self.assertEqual(load_config(directory)["odoo"]["http_port"], 8069)

        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            raw_config = {"tool": {"other": True}}
            save_config(directory, raw_config)

            self.assertEqual(load_config(directory), raw_config)


class WorkspaceDiscoveryTests(unittest.TestCase):
    def test_finds_workspace_root_from_nested_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "odoo" / "addons" / "sale"
            nested.mkdir(parents=True)
            save_config(root, minimal_workspace_config())

            self.assertEqual(find_workspace_root(nested), root.resolve())

    def test_ignores_non_workspace_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "odoo"
            nested.mkdir()
            save_config(root, minimal_workspace_config())
            save_config(nested, {"tool": {"other": True}})

            self.assertEqual(find_workspace_root(nested), root.resolve())

    def test_returns_none_outside_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(find_workspace_root(Path(tmp)))


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
