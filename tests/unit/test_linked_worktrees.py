import os
import tempfile
import unittest
from pathlib import Path

from odoo_cli.core.errors import (
    RepositoryNotFound,
    VersionNotFound,
    WorktreeNotFound,
)
from odoo_cli.core.models import Workspace, Worktree
from odoo_cli.core.repositories import RepositoryService
from odoo_cli.core.worktrees import WorktreeService
from odoo_cli.util.git import Git
from tests.fixtures.process import FakeProcessRunner
from tests.fixtures.workspace import make_worktree, make_workspace


class LinkedWorktreeTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)
        self.runner = FakeProcessRunner()
        git = Git(self.runner)
        self.service = WorktreeService(git, RepositoryService(git))
        self.root = make_workspace(
            self.home,
            repos=("odoo", "documentation", "enterprise", "customer-a-addons"),
        )
        self.workspace = Workspace(root=self.root, config=None)
        make_worktree(
            self.root, "19.0", version="19.0",
            repos=("documentation", "enterprise"),
        )
        # broad git fallback (remote_url, rev-parse, worktree add)
        self.runner.expect("git", stdout="ok")

    def repo_path(self, name):
        return str(self.root / ".repositories" / f"{name}.git")


class TestCreateLinked(LinkedWorktreeTestCase):
    def test_symlinks_and_addon_checkout(self):
        # no leftover 'customer-a' branch in the addon repo -> -b from 19.0
        self.runner.expect(
            "git", "-C", self.repo_path("customer-a-addons"), "rev-parse",
            "--verify", "--quiet", "refs/heads/customer-a", returncode=1,
        )
        result = self.service.create_linked(
            self.workspace, "customer-a", "19.0", "19.0", ["customer-a-addons"]
        )
        path = self.root / "customer-a"
        self.assertEqual(result.linked, ["odoo", "documentation", "enterprise"])
        self.assertEqual(result.checked_out, ["customer-a-addons"])
        self.assertEqual(result.warnings, [])
        self.assertEqual(os.readlink(path / "odoo"), "../19.0/odoo")
        self.assertEqual(os.readlink(path / "enterprise"), "../19.0/enterprise")
        # addon checked out on a branch named after the worktree, from 19.0
        self.assertIn(
            (
                "git", "-C", self.repo_path("customer-a-addons"), "worktree",
                "add", "-b", "customer-a", str(path / "customer-a-addons"),
                "19.0",
            ),
            self.runner.calls,
        )
        wt = Worktree(name="customer-a", path=path)
        self.assertTrue(wt.is_linked)
        self.assertEqual(wt.linked_from, "19.0")

    def test_addon_falls_back_to_default_branch_with_warning(self):
        repo = self.repo_path("customer-a-addons")
        self.runner.expect("git", "-C", repo, "rev-parse", returncode=1)
        self.runner.expect("git", "-C", repo, "symbolic-ref", stdout="main\n")
        result = self.service.create_linked(
            self.workspace, "customer-a", "19.0", "19.0", ["customer-a-addons"]
        )
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("default", result.warnings[0])
        add = next(c for c in self.runner.calls if "worktree" in c and "add" in c)
        self.assertEqual(add[-1], "main")

    def test_version_must_match_source(self):
        with self.assertRaises(VersionNotFound) as cm:
            self.service.create_linked(
                self.workspace, "customer-a", "18.0", "19.0", []
            )
        self.assertIn("19.0", cm.exception.message)

    def test_source_must_exist(self):
        with self.assertRaises(WorktreeNotFound):
            self.service.create_linked(
                self.workspace, "customer-a", "19.0", "nope", []
            )

    def test_unknown_addon_fails_before_creating_anything(self):
        with self.assertRaises(RepositoryNotFound):
            self.service.create_linked(
                self.workspace, "customer-a", "19.0", "19.0", ["unknown"]
            )
        self.assertFalse((self.root / "customer-a").exists())


class TestAddRepository(LinkedWorktreeTestCase):
    def worktree(self, name) -> Worktree:
        return Worktree(name=name, path=self.root / name)

    def test_added_to_full_worktree(self):
        # remove pre-existing enterprise dir to exercise the checkout
        os.rmdir(self.root / "19.0" / "enterprise")
        result = self.service.add_repository(
            self.workspace, self.worktree("19.0"), "enterprise"
        )
        self.assertTrue(result.added)

    def test_skips_linked_worktree(self):
        make_worktree(self.root, "customer-a", linked_from="19.0")
        result = self.service.add_repository(
            self.workspace, self.worktree("customer-a"), "enterprise"
        )
        self.assertFalse(result.added)
        self.assertIn("linked", result.reason)
        self.assertIn("19.0", result.reason)

    def test_skips_already_present(self):
        result = self.service.add_repository(
            self.workspace, self.worktree("19.0"), "enterprise"
        )
        self.assertFalse(result.added)
        self.assertEqual(result.reason, "already present")

    def test_skips_missing_version(self):
        os.rmdir(self.root / "19.0" / "enterprise")
        self.runner.expect(
            "git", "-C", self.repo_path("enterprise"), "rev-parse", returncode=1
        )
        result = self.service.add_repository(
            self.workspace, self.worktree("19.0"), "enterprise"
        )
        self.assertFalse(result.added)
        self.assertIn("no branch '19.0'", result.reason)
