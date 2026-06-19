import tempfile
import unittest
from pathlib import Path

from odoo_cli.core.errors import VersionNotFound, WorktreeExists
from odoo_cli.core.models import Workspace
from odoo_cli.core.repositories import RepositoryService
from odoo_cli.core.worktrees import WorktreeService, infer_base_version
from odoo_cli.util.git import Git
from odoo_cli.util.process import ProcessError
from tests.fixtures.process import FakeProcessRunner
from tests.fixtures.workspace import make_workspace, make_worktree


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


class TestInferBaseVersion(unittest.TestCase):
    def test_exact_versions(self):
        self.assertEqual(infer_base_version("master"), "master")
        self.assertEqual(infer_base_version("19.0"), "19.0")
        self.assertEqual(infer_base_version("6.1"), "6.1")
        self.assertEqual(infer_base_version("saas-17"), "saas-17")
        self.assertEqual(infer_base_version("saas-19.3"), "saas-19.3")

    def test_prefixed_worktree_names(self):
        self.assertEqual(infer_base_version("master-ux-polish"), "master")
        self.assertEqual(infer_base_version("19.0-my-worktree"), "19.0")
        self.assertEqual(infer_base_version("saas-19.3-fix"), "saas-19.3")

    def test_forward_port_style_uses_first_version(self):
        self.assertEqual(infer_base_version("19.0-18.0-fix-fw"), "19.0")
        self.assertEqual(infer_base_version("master-19.0-fix-fw"), "master")
        self.assertEqual(
            infer_base_version("saas-19.2-saas-19.1-fix-fw"), "saas-19.2"
        )

    def test_non_prefix_names_do_not_match(self):
        self.assertIsNone(infer_base_version("my-feature"))
        self.assertIsNone(infer_base_version("customer-19.0"))
        self.assertIsNone(infer_base_version("masterfoo"))
        self.assertIsNone(infer_base_version("saas-19.3foo"))


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

    def test_existing_directory_with_user_data_fails(self):
        ws = self.workspace()
        (ws.root / "19.0").mkdir()
        (ws.root / "19.0" / "notes.txt").write_text("keep me\n")
        with self.assertRaises(WorktreeExists):
            self.service.create_full(ws, "19.0", "19.0")
        self.assertTrue((ws.root / "19.0" / "notes.txt").is_file())

    def test_existing_empty_directory_is_repaired(self):
        # an empty directory is the leftover of a creation interrupted
        # right after mkdir; removing it loses nothing
        ws = self.workspace()
        (ws.root / "19.0").mkdir()
        self.allow_remote_urls()
        result = self.service.create_full(ws, "19.0", "19.0")
        self.assertEqual(result.checked_out, ["odoo", "documentation"])
        self.assertTrue(any("recreating" in w for w in result.warnings))

    def test_interrupted_creation_leftover_is_repaired(self):
        # partial checkout (broken gitdir) from a previous Ctrl-C
        ws = self.workspace()
        incomplete = ws.root / "19.0" / "odoo"
        incomplete.mkdir(parents=True)
        (incomplete / ".git").write_text("gitdir: broken\n")
        self.allow_remote_urls()
        result = self.service.create_full(ws, "19.0", "19.0")
        self.assertEqual(result.checked_out, ["odoo", "documentation"])
        self.assertTrue(any("recreating" in w for w in result.warnings))

    def test_create_prunes_stale_registrations_first(self):
        # `rm -rf <worktree>` leaves git registrations that block the same
        # worktree from being created again until a prune runs
        ws = self.workspace()
        self.allow_remote_urls()
        self.service.create_full(ws, "19.0", "19.0")
        prunes = [c for c in self.runner.calls if c[-2:] == ("worktree", "prune")]
        adds = [c for c in self.runner.calls if ("worktree", "add") == c[3:5]]
        self.assertTrue(prunes, "no prune before checkout")
        self.assertLess(
            self.runner.calls.index(prunes[0]),
            self.runner.calls.index(adds[0]),
            "prune must happen before the first checkout",
        )

    def test_rerun_completes_missing_standard_checkout(self):
        # interrupted after `odoo` finished: the worktree is valid but
        # incomplete; re-running create adds only what is missing
        ws = self.workspace()
        make_worktree(ws.root, "19.0", version="19.0", repos=())
        self.allow_remote_urls()
        result = self.service.create_full(ws, "19.0", "19.0")
        self.assertTrue(result.existed)
        self.assertEqual(result.checked_out, ["documentation"])
        add = next(c for c in self.runner.calls if c[3:5] == ("worktree", "add"))
        self.assertIn(str(ws.root / "19.0" / "documentation"), add)

    def test_rerun_with_wrong_version_fails(self):
        ws = self.workspace()
        make_worktree(ws.root, "myft", version="19.0")
        with self.assertRaises(WorktreeExists):
            self.service.create_full(ws, "myft", "18.0")

    def test_full_create_on_linked_worktree_fails(self):
        ws = self.workspace()
        make_worktree(ws.root, "19.0", version="19.0")
        make_worktree(ws.root, "cust", linked_from="19.0")
        with self.assertRaises(WorktreeExists):
            self.service.create_full(ws, "cust", "19.0")

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
