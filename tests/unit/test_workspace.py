import tempfile
import unittest
from pathlib import Path

from odoo_cli.core import paths
from odoo_cli.core.errors import WorkspaceNotFound
from odoo_cli.core.workspace import WorkspaceResolver
from tests.fixtures.workspace import make_env, make_workspace


class WorkspaceTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)
        self.env = make_env(self.home)


class TestPaths(WorkspaceTestCase):
    def test_default_root(self):
        self.assertEqual(paths.workspace_root(self.env), self.home / "odoo")

    def test_odoo_dir_override(self):
        env = make_env(self.home, ODOO_DIR=str(self.home / "elsewhere"))
        self.assertEqual(paths.workspace_root(env), self.home / "elsewhere")

    def test_conf_path_default(self):
        self.assertEqual(
            paths.odoo_conf_path(self.env),
            self.home / ".config" / "odoo" / "odoo.conf",
        )

    def test_conf_path_xdg(self):
        env = make_env(self.home, XDG_CONFIG_HOME=str(self.home / "xdg"))
        self.assertEqual(
            paths.odoo_conf_path(env), self.home / "xdg" / "odoo" / "odoo.conf"
        )


class TestWorkspaceResolver(WorkspaceTestCase):
    def test_missing_workspace(self):
        with self.assertRaises(WorkspaceNotFound) as cm:
            WorkspaceResolver(self.env).resolve()
        self.assertIn("odoo init", cm.exception.hint)

    def test_resolve_valid_workspace(self):
        root = make_workspace(self.home)
        ws = WorkspaceResolver(self.env).resolve()
        self.assertEqual(ws.root, root)
        self.assertEqual(ws.repositories_dir, root / ".repositories")

    def test_create_skeleton_is_idempotent(self):
        resolver = WorkspaceResolver(self.env)
        root = resolver.create_skeleton()
        resolver.create_skeleton()
        for name in (".repositories", ".venvs", ".run"):
            self.assertTrue((root / name).is_dir())
        # skeleton alone is not a workspace yet
        with self.assertRaises(WorkspaceNotFound):
            resolver.resolve()

    def test_ensure_default_conf_creates_once(self):
        resolver = WorkspaceResolver(self.env)
        created, missing = resolver.ensure_default_conf()
        self.assertTrue(created)
        self.assertEqual(missing, [])
        conf_path = resolver.conf_path
        conf_path.write_text("[options]\ndb_host = localhost\ndev_mode = all\n")
        created, missing = resolver.ensure_default_conf()
        self.assertFalse(created)
        self.assertIn("log_level", missing)
        self.assertNotIn("dev_mode", missing)
        # the existing file was not modified
        self.assertEqual(
            conf_path.read_text(), "[options]\ndb_host = localhost\ndev_mode = all\n"
        )

    def test_rcfile_warnings(self):
        resolver = WorkspaceResolver(self.env)
        self.assertEqual(resolver.rcfile_warnings(), [])
        (self.home / ".odoorc").write_text("")
        env = make_env(self.home, ODOO_RC="/etc/odoo.conf")
        warnings = WorkspaceResolver(env).rcfile_warnings()
        self.assertEqual(len(warnings), 2)
        self.assertIn(".odoorc", warnings[0])
        self.assertIn("ODOO_RC", warnings[1])
