"""OdooBinService is the wrapper around a version-dependent external
interface; these tests pin the generated command per purpose and version."""

import tempfile
import unittest
from pathlib import Path

from odoo_cli.core.errors import UnsupportedOdooVersion
from odoo_cli.core.models import Ports, Target, Workspace, Worktree
from odoo_cli.core.odoo_bin import OdooBinService, capabilities_for
from tests.fixtures.workspace import make_env, make_worktree, make_workspace


class OdooBinTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)
        self.root = make_workspace(self.home)
        self.env = make_env(self.home)
        self.service = OdooBinService(self.env)
        self.python = Path("/venvs/19.0/bin/python")
        self.conf = str(self.home / ".config" / "odoo" / "odoo.conf")

    def target(self, version="19.0", name="wt", db=None) -> Target:
        path = make_worktree(self.root, name, version=version)
        worktree = Worktree(name=name, path=path)
        return Target(
            workspace=Workspace(root=self.root, config=None),
            worktree=worktree,
            database=db or name,
        )

    def base(self, target, db=None):
        return [
            "-c", self.conf,
            "-d", db or target.database,
            "--addons-path", str(target.worktree.path / "odoo" / "addons"),
        ]

    def bin_prefix(self, target):
        return [str(self.python), str(target.worktree.path / "odoo" / "odoo-bin")]


class TestCapabilities(unittest.TestCase):
    def test_supported_versions(self):
        for version in ("17.0", "18.0", "19.0", "saas-19.4"):
            self.assertFalse(capabilities_for(version).native_module_install)
        self.assertTrue(capabilities_for("20.0").native_module_install)
        self.assertTrue(capabilities_for("saas-20.1").native_module_install)

    def test_unsupported_version(self):
        for version in ("16.0", "15.0", "saas-16.4"):
            with self.assertRaises(UnsupportedOdooVersion):
                capabilities_for(version)


class TestServerStart(OdooBinTestCase):
    def test_argv(self):
        target = self.target()
        cmd = self.service.server_start(
            target, python=self.python, ports=Ports(http=8069, gevent=8072)
        )
        self.assertEqual(
            cmd.argv,
            self.bin_prefix(target) + self.base(target)
            + ["--http-port", "8069", "--gevent-port", "8072"],
        )
        self.assertEqual(cmd.cwd, target.worktree.path / "odoo")
        self.assertEqual(cmd.env, {})
        self.assertEqual(cmd.redacted_argv, cmd.argv)

    def test_prod_disables_dev_mode(self):
        target = self.target()
        cmd = self.service.server_start(
            target, python=self.python, ports=Ports(8069, 8072), prod=True
        )
        self.assertEqual(cmd.argv[-2:], ["--dev", "none"])

    def test_unsupported_version_raises(self):
        target = self.target(version="16.0", name="old")
        with self.assertRaises(UnsupportedOdooVersion):
            self.service.server_start(
                target, python=self.python, ports=Ports(8069, 8072)
            )


class TestDbInit(OdooBinTestCase):
    def test_argv(self):
        target = self.target()
        cmd = self.service.db_init(target, python=self.python)
        self.assertEqual(
            cmd.argv,
            self.bin_prefix(target) + self.base(target)
            + ["--stop-after-init", "--no-http"],
        )


class TestModuleInstall(OdooBinTestCase):
    def test_polyfill_on_supported_stables(self):
        for version in ("17.0", "18.0", "19.0"):
            target = self.target(version=version, name=f"wt{version}")
            cmd = self.service.module_install(
                target, ["crm", "sale"], python=self.python
            )
            self.assertEqual(
                cmd.argv,
                self.bin_prefix(target) + self.base(target)
                + ["-i", "crm,sale", "--stop-after-init", "--no-http"],
            )

    def test_native_on_master_line(self):
        target = self.target(version="20.0", name="master")
        cmd = self.service.module_install(target, ["crm"], python=self.python)
        self.assertEqual(
            cmd.argv,
            self.bin_prefix(target)
            + ["module", "install", "crm"] + self.base(target),
        )


class TestModuleUpdate(OdooBinTestCase):
    def test_default_updates_all(self):
        target = self.target()
        cmd = self.service.module_update(target, None, python=self.python)
        self.assertIn("-u", cmd.argv)
        self.assertEqual(cmd.argv[cmd.argv.index("-u") + 1], "all")

    def test_specific_modules(self):
        target = self.target()
        cmd = self.service.module_update(target, ["sale"], python=self.python)
        self.assertEqual(cmd.argv[cmd.argv.index("-u") + 1], "sale")


class TestTests(OdooBinTestCase):
    def test_uses_test_database(self):
        target = self.target()
        cmd = self.service.tests(target, ["crm"], python=self.python)
        self.assertEqual(cmd.argv[cmd.argv.index("-d") + 1], "wt-test")
        self.assertIn("--test-enable", cmd.argv)
        self.assertNotIn("--no-http", cmd.argv)  # HttpCase needs http

    def test_tag_resolution(self):
        target = self.target()
        cmd = self.service.tests(
            target, ["crm"], ["test_lead_creation", "at_install"],
            python=self.python,
        )
        tags = cmd.argv[cmd.argv.index("--test-tags") + 1]
        self.assertEqual(tags, ".test_lead_creation,at_install")
        self.assertNotIn("--test-enable", cmd.argv)


class TestShell(OdooBinTestCase):
    def test_argv(self):
        target = self.target()
        cmd = self.service.shell(target, python=self.python)
        self.assertEqual(
            cmd.argv,
            self.bin_prefix(target) + ["shell"] + self.base(target) + ["--no-http"],
        )
