import os
import tempfile
import unittest
from pathlib import Path

from odoo_cli.core.errors import TargetAmbiguous, WorktreeNotFound
from odoo_cli.core.target import TargetResolver
from odoo_cli.core.workspace import WorkspaceResolver
from tests.fixtures.workspace import make_env, make_workspace, make_worktree


class TargetTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        # macOS: /var/folders is a symlink; resolve so path comparisons in
        # tests reflect what a user's logical paths look like
        self.home = Path(self._tmp.name).resolve()
        self.root = make_workspace(self.home)
        self._original_cwd = os.getcwd()
        self.addCleanup(os.chdir, self._original_cwd)
        os.chdir(self.home)  # default: outside the workspace

    def resolver(self, **env_extra):
        env = make_env(self.home, **env_extra)
        return TargetResolver(WorkspaceResolver(env), env)

    def chdir(self, path: Path, logical: Path | None = None):
        os.chdir(path)
        return self.resolver(PWD=str(logical or path))


class TestWorktreeResolution(TargetTestCase):
    def test_explicit_worktree(self):
        make_worktree(self.root, "19.0", version="19.0")
        make_worktree(self.root, "master", version="saas-19.4")
        target = self.resolver().resolve(worktree="master")
        self.assertEqual(target.worktree.name, "master")
        self.assertEqual(target.database, "master")

    def test_explicit_worktree_not_found(self):
        make_worktree(self.root, "19.0", version="19.0")
        with self.assertRaises(WorktreeNotFound) as cm:
            self.resolver().resolve(worktree="nope")
        self.assertIn("19.0", cm.exception.hint)

    def test_only_worktree_rule(self):
        make_worktree(self.root, "19.0", version="19.0")
        target = self.resolver().resolve()
        self.assertEqual(target.worktree.name, "19.0")

    def test_no_worktrees(self):
        with self.assertRaises(WorktreeNotFound) as cm:
            self.resolver().resolve()
        self.assertIn("worktree create", cm.exception.hint)

    def test_ambiguous_lists_worktrees(self):
        make_worktree(self.root, "19.0", version="19.0")
        make_worktree(self.root, "master", version="saas-19.4")
        with self.assertRaises(TargetAmbiguous) as cm:
            self.resolver().resolve()
        self.assertIn("19.0", cm.exception.hint)
        self.assertIn("master", cm.exception.hint)
        self.assertIn("--worktree", cm.exception.hint)

    def test_cwd_inside_worktree(self):
        make_worktree(self.root, "19.0", version="19.0")
        make_worktree(self.root, "master", version="saas-19.4")
        deep = self.root / "19.0" / "odoo" / "odoo"
        resolver = self.chdir(deep)
        target = resolver.resolve()
        self.assertEqual(target.worktree.name, "19.0")

    def test_cwd_inside_linked_worktree_targets_link(self):
        make_worktree(self.root, "19.0", version="19.0")
        make_worktree(self.root, "customer-a", linked_from="19.0")
        # physically inside 19.0/odoo, logically inside customer-a/odoo
        logical = self.root / "customer-a" / "odoo" / "odoo"
        physical = self.root / "19.0" / "odoo" / "odoo"
        resolver = self.chdir(physical, logical=logical)
        target = resolver.resolve()
        self.assertEqual(target.worktree.name, "customer-a")
        self.assertEqual(target.database, "customer-a")

    def test_stale_pwd_falls_back_to_physical(self):
        make_worktree(self.root, "19.0", version="19.0")
        make_worktree(self.root, "master", version="saas-19.4")
        resolver = self.chdir(
            self.root / "master", logical=self.root / "19.0" / "odoo"
        )
        target = resolver.resolve()
        self.assertEqual(target.worktree.name, "master")

    def test_workspace_root_is_not_a_worktree(self):
        make_worktree(self.root, "19.0", version="19.0")
        make_worktree(self.root, "master", version="saas-19.4")
        resolver = self.chdir(self.root)
        with self.assertRaises(TargetAmbiguous):
            resolver.resolve()

    def test_non_worktree_dir_is_ignored(self):
        make_worktree(self.root, "19.0", version="19.0")
        (self.root / "dumps").mkdir()
        resolver = self.chdir(self.root / "dumps")
        target = resolver.resolve()  # falls through to only-worktree rule
        self.assertEqual(target.worktree.name, "19.0")


class TestDatabaseResolution(TargetTestCase):
    def test_default_is_worktree_name(self):
        make_worktree(self.root, "fix-pos-flow", version="19.0")
        target = self.resolver().resolve()
        self.assertEqual(target.database, "fix-pos-flow")
        self.assertEqual(target.test_database, "fix-pos-flow-test")

    def test_explicit_db(self):
        make_worktree(self.root, "19.0", version="19.0")
        target = self.resolver().resolve(db="customer-a")
        self.assertEqual(target.database, "customer-a")
