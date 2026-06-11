import tempfile
import unittest
from pathlib import Path

from odoo_cli.core.errors import VersionNotFound, WorktreeExists
from odoo_cli.core.models import Workspace
from odoo_cli.core.repositories import RepositoryService
from odoo_cli.core.worktrees import WorktreeService
from odoo_cli.util.git import Git
from odoo_cli.util.process import ProcessError
from tests.fixtures.process import FakeProcessRunner
from tests.fixtures.workspace import make_workspace


class WorktreeServiceTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)
        self.runner = FakeProcessRunner()
        git = Git(self.runner)
        self.service = WorktreeService(git, RepositoryService(git))

    def workspace(self, repos=("odoo", "documentation")):
        return Workspace(root=make_workspace(self.home, repos=repos), config=None)

    def repo_path(self, ws, name):
        return str(ws.root / ".repositories" / f"{name}.git")

    def allow_remote_urls(self):
        self.runner.expect("git", stdout="https://example.com/x.git\n")


class TestCreateFull(WorktreeServiceTestCase):
    def test_name_equals_version_checks_out_branch(self):
        ws = self.workspace()
        self.allow_remote_urls()
        result = self.service.create_full(ws, "19.0", "19.0")
        self.assertEqual(result.checked_out, ["odoo", "documentation"])
        self.assertEqual(result.skipped, [])
        self.assertIn(
            (
                "git", "-C", self.repo_path(ws, "odoo"), "worktree", "add",
                str(ws.root / "19.0" / "odoo"), "19.0",
            ),
            self.runner.calls,
        )

    def test_feature_worktree_creates_branch_from_version(self):
        ws = self.workspace()
        self.allow_remote_urls()
        # branch_exists(fix-pos-flow) -> no; branch_exists(19.0) -> yes
        self.runner.expect("git", "-C", self.repo_path(ws, "odoo"), "rev-parse")
        self.runner.expect(
            "git", "-C", self.repo_path(ws, "odoo"), "rev-parse", "--verify",
            "--quiet", "refs/heads/fix-pos-flow", returncode=1,
        )
        self.runner.expect(
            "git", "-C", self.repo_path(ws, "documentation"), "rev-parse"
        )
        self.runner.expect(
            "git", "-C", self.repo_path(ws, "documentation"), "rev-parse",
            "--verify", "--quiet", "refs/heads/fix-pos-flow", returncode=1,
        )
        result = self.service.create_full(ws, "fix-pos-flow", "19.0")
        self.assertEqual(result.checked_out, ["odoo", "documentation"])
        self.assertIn(
            (
                "git", "-C", self.repo_path(ws, "odoo"), "worktree", "add",
                "-b", "fix-pos-flow", str(ws.root / "fix-pos-flow" / "odoo"),
                "19.0",
            ),
            self.runner.calls,
        )

    def test_optional_repo_without_version_is_skipped(self):
        ws = self.workspace(repos=("odoo", "documentation", "enterprise"))
        self.allow_remote_urls()
        self.runner.expect(
            "git", "-C", self.repo_path(ws, "enterprise"), "rev-parse",
            returncode=1,
        )
        result = self.service.create_full(ws, "19.0", "19.0")
        self.assertEqual(result.checked_out, ["odoo", "documentation"])
        self.assertEqual(len(result.skipped), 1)
        self.assertEqual(result.skipped[0].name, "enterprise")
        self.assertIn("19.0", result.skipped[0].reason)

    def test_odoo_without_version_fails(self):
        ws = self.workspace()
        self.allow_remote_urls()
        self.runner.expect(
            "git", "-C", self.repo_path(ws, "odoo"), "rev-parse", returncode=1
        )
        with self.assertRaises(VersionNotFound):
            self.service.create_full(ws, "6.1", "6.1")

    def test_existing_directory_fails(self):
        ws = self.workspace()
        (ws.root / "19.0").mkdir()
        with self.assertRaises(WorktreeExists):
            self.service.create_full(ws, "19.0", "19.0")

    def test_failed_checkout_cleans_partial_directory_and_prunes(self):
        ws = self.workspace()
        self.allow_remote_urls()

        def fail_after_partial_checkout(call):
            dest = Path(call[5])
            dest.mkdir(parents=True, exist_ok=True)
            (dest / ".git").write_text("gitdir: broken\n")

        self.runner.expect(
            "git",
            "-C",
            self.repo_path(ws, "odoo"),
            "worktree",
            "add",
            returncode=128,
            effect=fail_after_partial_checkout,
        )

        with self.assertRaises(ProcessError):
            self.service.create_full(ws, "19.0", "19.0")

        self.assertFalse((ws.root / "19.0").exists())
        self.assertTrue(any(c[-2:] == ("worktree", "prune") for c in self.runner.calls))
