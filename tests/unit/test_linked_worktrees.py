import os
import tempfile
import unittest
from pathlib import Path

from odoo_cli.core.errors import (
    RepositoryNotFound,
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
            self.workspace, "customer-a", "19.0", ["customer-a-addons"]
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
            self.workspace, "customer-a", "19.0", ["customer-a-addons"]
        )
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("default", result.warnings[0])
        add = next(c for c in self.runner.calls if "worktree" in c and "add" in c)
        self.assertEqual(add[-1], "main")

    def test_linked_source_is_rejected(self):
        # symlink chains break silently when the middle worktree is removed
        from odoo_cli.core.errors import OdooCliError

        make_worktree(self.root, "customer-a", linked_from="19.0")
        with self.assertRaises(OdooCliError) as cm:
            self.service.create_linked(
                self.workspace, "customer-b", "customer-a", []
            )
        self.assertIn("linked worktree", cm.exception.message)
        self.assertIn("19.0", cm.exception.hint)
        self.assertFalse((self.root / "customer-b").exists())

    def test_source_must_exist(self):
        with self.assertRaises(WorktreeNotFound):
            self.service.create_linked(
                self.workspace, "customer-a", "nope", []
            )

    def test_unknown_addon_fails_before_creating_anything(self):
        with self.assertRaises(RepositoryNotFound):
            self.service.create_linked(
                self.workspace, "customer-a", "19.0", ["unknown"]
            )
        self.assertFalse((self.root / "customer-a").exists())

    def test_standard_repo_as_addon_fails_before_creating_anything(self):
        # enterprise would be symlinked first and then collide with its own
        # checkout; reject it up front with a clear message instead
        from odoo_cli.core.errors import OdooCliError

        with self.assertRaises(OdooCliError) as cm:
            self.service.create_linked(
                self.workspace, "customer-a", "19.0", ["enterprise"]
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
                self.workspace, "customer-a", "19.0",
                ["customer-a-addons"],
            )
        # symlinks were created before the failure; everything is rolled back
        self.assertFalse((self.root / "customer-a").exists())
        prunes = [c for c in self.runner.calls if c[-1] == "prune"]
        self.assertTrue(prunes)


class TestCreateDuplicate(LinkedWorktreeTestCase):
    def expect_branch(self, worktree, repo, branch):
        path = str(self.root / worktree / repo)
        self.runner.expect(
            "git", "-C", path, "symbolic-ref", stdout=f"{branch}\n"
        )

    def expect_no_leftover_branch(self, repo, name):
        self.runner.expect(
            "git", "-C", self.repo_path(repo), "rev-parse",
            "--verify", "--quiet", f"refs/heads/{name}", returncode=1,
        )

    def test_duplicates_every_repo_from_source_branches(self):
        for repo in ("odoo", "documentation", "enterprise"):
            self.expect_branch("19.0", repo, "19.0")
            self.expect_no_leftover_branch(repo, "fix-pos")

        result = self.service.create_duplicate(self.workspace, "fix-pos", "19.0")

        self.assertEqual(
            result.checked_out, ["odoo", "documentation", "enterprise"]
        )
        self.assertEqual(result.linked, [])
        self.assertIn(
            (
                "git", "-C", self.repo_path("odoo"), "worktree", "add", "-b",
                "fix-pos", str(self.root / "fix-pos" / "odoo"), "19.0",
            ),
            self.runner.calls,
        )

    def test_detached_source_branches_from_the_commit(self):
        odoo_dir = str(self.root / "19.0" / "odoo")
        self.runner.expect("git", "-C", odoo_dir, "symbolic-ref", returncode=1)
        self.runner.expect(
            "git", "-C", odoo_dir, "rev-parse", "HEAD", stdout="abc123\n"
        )
        for repo in ("documentation", "enterprise"):
            self.expect_branch("19.0", repo, "19.0")
        for repo in ("odoo", "documentation", "enterprise"):
            self.expect_no_leftover_branch(repo, "fix-pos")

        self.service.create_duplicate(self.workspace, "fix-pos", "19.0")

        add = next(
            c for c in self.runner.calls
            if "add" in c and str(self.root / "fix-pos" / "odoo") in c
        )
        self.assertEqual(add[-1], "abc123")

    def test_non_repo_entries_are_skipped_or_ignored(self):
        tools = self.root / "19.0" / "support-tools"
        tools.mkdir()
        (tools / ".git").write_text("gitdir: elsewhere\n")
        (self.root / "19.0" / "dumps").mkdir()
        (self.root / "19.0" / "notes.txt").write_text("x\n")
        for repo in ("odoo", "documentation", "enterprise"):
            self.expect_branch("19.0", repo, "19.0")
            self.expect_no_leftover_branch(repo, "fix-pos")

        result = self.service.create_duplicate(self.workspace, "fix-pos", "19.0")

        self.assertEqual([s.name for s in result.skipped], ["support-tools"])
        self.assertIn("no repository", result.skipped[0].reason)
        self.assertFalse((self.root / "fix-pos" / "dumps").exists())

    def test_duplicate_of_linked_worktree_links_to_the_original(self):
        make_worktree(
            self.root, "customer-a", linked_from="19.0",
            repos=("documentation", "enterprise"),
        )
        (self.root / "customer-a" / "customer-a-addons").mkdir()
        self.expect_branch("customer-a", "customer-a-addons", "customer-a")
        self.expect_no_leftover_branch("customer-a-addons", "customer-b")

        result = self.service.create_duplicate(
            self.workspace, "customer-b", "customer-a"
        )

        path = self.root / "customer-b"
        self.assertEqual(result.linked, ["odoo", "documentation", "enterprise"])
        self.assertEqual(result.checked_out, ["customer-a-addons"])
        # linked to the original, not chained through customer-a
        self.assertEqual(os.readlink(path / "odoo"), "../19.0/odoo")
        wt = Worktree(name="customer-b", path=path)
        self.assertTrue(wt.is_linked)
        self.assertEqual(wt.linked_from, "19.0")
        # the addon branches from customer-a's branch, not from 19.0
        self.assertIn(
            (
                "git", "-C", self.repo_path("customer-a-addons"), "worktree",
                "add", "-b", "customer-b",
                str(path / "customer-a-addons"), "customer-a",
            ),
            self.runner.calls,
        )

    def test_rerun_adds_missing_repos_only(self):
        make_worktree(
            self.root, "fix-pos", version="19.0", repos=("documentation",)
        )
        for repo in ("odoo", "documentation", "enterprise"):
            self.expect_branch("19.0", repo, "19.0")
        self.expect_no_leftover_branch("enterprise", "fix-pos")

        result = self.service.create_duplicate(self.workspace, "fix-pos", "19.0")

        self.assertTrue(result.existed)
        self.assertEqual(result.checked_out, ["enterprise"])

    def test_rerun_with_different_version_fails(self):
        from odoo_cli.core.errors import WorktreeExists

        make_worktree(self.root, "fix-pos", version="18.0")
        with self.assertRaises(WorktreeExists) as cm:
            self.service.create_duplicate(self.workspace, "fix-pos", "19.0")
        self.assertIn("18.0", cm.exception.message)

    def test_rerun_nature_mismatch_fails(self):
        from odoo_cli.core.errors import WorktreeExists

        make_worktree(self.root, "customer-b", linked_from="19.0")
        with self.assertRaises(WorktreeExists) as cm:
            self.service.create_duplicate(self.workspace, "customer-b", "19.0")
        self.assertIn("linked", cm.exception.message)

    def test_source_must_exist(self):
        with self.assertRaises(WorktreeNotFound):
            self.service.create_duplicate(self.workspace, "x", "nope")


class TestCompleteLinked(LinkedWorktreeTestCase):
    def test_rerun_checks_out_missing_addon(self):
        # interrupted after the symlinks: the linked worktree is valid but
        # has no addon checkout; the re-run adds only the addon
        make_worktree(
            self.root, "customer-a", linked_from="19.0",
            repos=("documentation", "enterprise"),
        )
        result = self.service.create_linked(
            self.workspace, "customer-a", "19.0", ["customer-a-addons"]
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
                self.workspace, "customer-a", "other", []
            )

    def test_leftover_with_dangling_symlinks_is_repaired(self):
        # the source worktree of an interrupted linked create was removed:
        # only dangling symlinks remain, provably ours, safe to recreate
        path = self.root / "customer-a"
        path.mkdir()
        os.symlink("../gone/odoo", path / "odoo")
        result = self.service.create_linked(
            self.workspace, "customer-a", "19.0", []
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

    def test_master_worktree_uses_master_branch(self):
        make_worktree(self.root, "master", version="saas-19.4", repos=())
        repo = self.repo_path("enterprise")
        self.runner.expect(
            "git", "-C", repo, "rev-parse", "--verify", "--quiet",
            "refs/heads/saas-19.4", returncode=1,
        )
        self.runner.expect(
            "git", "-C", repo, "rev-parse", "--verify", "--quiet",
            "refs/heads/master",
        )

        result = self.service.add_repository(
            self.workspace, self.worktree("master"), "enterprise"
        )

        self.assertTrue(result.added)
        self.assertIn(
            (
                "git", "-C", repo, "worktree", "add",
                str(self.root / "master" / "enterprise"), "master",
            ),
            self.runner.calls,
        )
