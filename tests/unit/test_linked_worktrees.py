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
from tests.fixtures.workspace import make_workspace, make_worktree


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

    def test_standard_repo_as_addon_fails_before_creating_anything(self):
        # enterprise would be symlinked first and then collide with its own
        # checkout; reject it up front with a clear message instead
        from odoo_cli.core.errors import OdooCliError

        with self.assertRaises(OdooCliError) as cm:
            self.service.create_linked(
                self.workspace, "customer-a", "19.0", "19.0", ["enterprise"]
            )
        self.assertIn("standard repository", cm.exception.message)
        self.assertFalse((self.root / "customer-a").exists())

    def test_failed_addon_checkout_removes_partial_linked_worktree(self):
        from odoo_cli.util.process import ProcessError

        repo = self.repo_path("customer-a-addons")
        self.runner.expect(
            "git", "-C", repo, "worktree", "add", returncode=128,
            stderr="fatal: could not fetch from promisor remote\n",
        )
        with self.assertRaises(ProcessError):
            self.service.create_linked(
                self.workspace, "customer-a", "19.0", "19.0",
                ["customer-a-addons"],
            )
        # symlinks were created before the failure; everything is rolled back
        self.assertFalse((self.root / "customer-a").exists())
        prunes = [c for c in self.runner.calls if c[-1] == "prune"]
        self.assertTrue(prunes)


class TestCompleteLinked(LinkedWorktreeTestCase):
    def test_rerun_checks_out_missing_addon(self):
        # interrupted after the symlinks: the linked worktree is valid but
        # has no addon checkout; the re-run adds only the addon
        make_worktree(
            self.root, "customer-a", linked_from="19.0",
            repos=("documentation", "enterprise"),
        )
        result = self.service.create_linked(
            self.workspace, "customer-a", "19.0", "19.0", ["customer-a-addons"]
        )
        self.assertTrue(result.existed)
        self.assertEqual(result.checked_out, ["customer-a-addons"])
        self.assertEqual(result.linked, [])  # symlinks were already in place
        self.assertTrue(
            (self.root / "customer-a" / "odoo").is_symlink()
        )

    def test_rerun_with_wrong_source_fails(self):
        from odoo_cli.core.errors import WorktreeExists

        make_worktree(self.root, "customer-a", linked_from="19.0")
        make_worktree(self.root, "other", version="19.0")
        with self.assertRaises(WorktreeExists):
            self.service.create_linked(
                self.workspace, "customer-a", "19.0", "other", []
            )

    def test_leftover_with_dangling_symlinks_is_repaired(self):
        # the source worktree of an interrupted linked create was removed:
        # only dangling symlinks remain, provably ours, safe to recreate
        path = self.root / "customer-a"
        path.mkdir()
        os.symlink("../gone/odoo", path / "odoo")
        result = self.service.create_linked(
            self.workspace, "customer-a", "19.0", "19.0", []
        )
        self.assertFalse(result.existed)
        self.assertEqual(result.linked, ["odoo", "documentation", "enterprise"])
        self.assertTrue(any("recreating" in w for w in result.warnings))


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
        dest = self.root / "19.0" / "enterprise"
        (dest / ".git").write_text("gitdir: x\n")
        self.runner.expect(
            "git", "-C", str(dest), "rev-parse", "--git-common-dir",
            stdout=f"{self.repo_path('enterprise')}\n",
        )
        result = self.service.add_repository(
            self.workspace, self.worktree("19.0"), "enterprise"
        )
        self.assertFalse(result.added)
        self.assertEqual(result.reason, "already present")

    def test_checkout_of_a_different_repository_is_reported(self):
        dest = self.root / "19.0" / "enterprise"
        (dest / ".git").write_text("gitdir: x\n")
        self.runner.expect(
            "git", "-C", str(dest), "rev-parse", "--git-common-dir",
            stdout=f"{self.repo_path('customer-a-addons')}\n",
        )
        result = self.service.add_repository(
            self.workspace, self.worktree("19.0"), "enterprise"
        )
        self.assertFalse(result.added)
        self.assertIn("different repository", result.reason)

    def test_broken_symlink_destination_is_reported(self):
        # exists() follows symlinks: a dangling one must not slip past the
        # guards into `git worktree add`
        os.rmdir(self.root / "19.0" / "enterprise")
        os.symlink("nowhere", self.root / "19.0" / "enterprise")
        result = self.service.add_repository(
            self.workspace, self.worktree("19.0"), "enterprise"
        )
        self.assertFalse(result.added)
        self.assertIn("broken symlink", result.reason)

    def test_broken_destination_is_reported_not_skipped_silently(self):
        # a directory without .git (failed earlier add) must not be reported
        # as already present
        result = self.service.add_repository(
            self.workspace, self.worktree("19.0"), "enterprise"
        )
        self.assertFalse(result.added)
        self.assertIn("not a git checkout", result.reason)

    def test_failed_checkout_cleans_destination_and_prunes(self):
        import shutil as _shutil

        _shutil.rmtree(self.root / "19.0" / "enterprise")
        repo = self.repo_path("enterprise")
        self.runner.expect(
            "git", "-C", repo, "worktree", "add", returncode=128,
            stderr="fatal: disk full\n",
            effect=lambda call: Path(call[5]).mkdir(parents=True, exist_ok=True),
        )
        from odoo_cli.util.process import ProcessError

        with self.assertRaises(ProcessError):
            self.service.add_repository(
                self.workspace, self.worktree("19.0"), "enterprise"
            )
        self.assertFalse((self.root / "19.0" / "enterprise").exists())
        self.assertIn(("git", "-C", repo, "worktree", "prune"), self.runner.calls)

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
