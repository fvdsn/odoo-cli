import json
import tempfile
import unittest
from pathlib import Path

from odoo_cli.cli._click import testing
from odoo_cli.cli.context import CliContext, Services
from odoo_cli.cli.main import cli
from odoo_cli.core.odoo_conf import REDACTED, write_defaults
from tests.fixtures.process import FakeProcessRunner
from tests.fixtures.workspace import make_env, make_workspace


class ConfigCommandTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name).resolve()
        self.env = make_env(self.home)
        self.conf_path = self.home / ".config" / "odoo" / "odoo.conf"
        write_defaults(self.conf_path)
        self.runner = FakeProcessRunner()
        self.runner.expect("git", stdout="https://example.com/r.git\n")
        self.cli_runner = testing.CliRunner()

    def invoke(self, *args):
        services = Services(process=self.runner, env=self.env)
        return self.cli_runner.invoke(cli, list(args), obj=CliContext(services=services))


class TestConfig(ConfigCommandTestCase):
    def test_set_then_get(self):
        result = self.invoke("config", "set", "db_user", "dev")
        self.assertEqual(result.exit_code, 0, result.output)
        result = self.invoke("config", "get", "db_user")
        self.assertEqual(result.output.strip(), "dev")

    def test_get_unset_key_fails(self):
        result = self.invoke("config", "get", "nope")
        self.assertEqual(result.exit_code, 1)
        # rendering happens in main(); CliRunner surfaces the raw error
        self.assertIn("config set", result.exception.hint)

    def test_get_reveals_secret(self):
        self.invoke("config", "set", "db_password", "hunter2")
        result = self.invoke("config", "get", "db_password")
        self.assertEqual(result.output.strip(), "hunter2")

    def test_list_redacts_by_default(self):
        self.invoke("config", "set", "db_password", "hunter2")
        result = self.invoke("config", "list")
        self.assertIn(REDACTED, result.output)
        self.assertNotIn("hunter2", result.output)
        reveal = self.invoke("config", "list", "--reveal")
        self.assertIn("hunter2", reveal.output)

    def test_list_does_not_redact_unset_password(self):
        # "False" is odoo's unset convention: not a secret, shown as-is
        self.invoke("config", "set", "db_password", "False")
        result = self.invoke("config", "list")
        self.assertIn("db_password = False", result.output)
        self.assertNotIn(REDACTED, result.output)

    def test_list_without_workspace(self):
        result = self.invoke("config", "list", "--json")
        data = json.loads(result.output)
        self.assertIsNone(data["repositories"])
        self.assertEqual(data["options"]["dev_mode"], "all")

    def test_list_shows_enabled_repos(self):
        make_workspace(self.home, repos=("odoo", "documentation", "enterprise"))
        result = self.invoke("config", "list", "--json")
        data = json.loads(result.output)
        self.assertEqual(
            data["repositories"]["enabled"],
            ["documentation", "enterprise", "odoo"],
        )
        self.assertEqual(data["repositories"]["available"], ["themes", "upgrade"])

    def test_set_help_mentions_comment_loss(self):
        result = self.invoke("config", "set", "--help")
        self.assertIn("comments", result.output)

    def test_set_preserves_unknown_keys(self):
        self.conf_path.write_text("[options]\nproxy_mode = True\n")
        self.invoke("config", "set", "db_user", "dev")
        content = self.conf_path.read_text()
        self.assertIn("proxy_mode = True", content)
        self.assertIn("db_user = dev", content)
