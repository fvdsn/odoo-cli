import tempfile
import unittest
from pathlib import Path

from odoo_cli.core.models import Workspace, Worktree
from odoo_cli.core.sync import ADVANCED, SKIPPED, UP_TO_DATE, PullService
from tests.fixtures.workspace import make_workspace, make_worktree


class _R:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class FakeGit:
    """Scripted by checkout dir name (odoo, documentation, …)."""

    def __init__(self):
        self.branch = "19.0"
        self.branch_by: dict[str, str | None] = {}
        self.dirty_names: set[str] = set()
        self.fetch_by: dict[str, _R] = {}
        self.merge_by: dict[str, _R] = {}
        self.heads_by: dict[str, list[str]] = {}

    def current_branch(self, p):
        return self.branch_by.get(p.name, self.branch)

    def is_dirty(self, p):
        return p.name in self.dirty_names

    def fetch_branch(self, p, base):
        return self.fetch_by.get(p.name, _R(0))

    def merge_ff_only(self, p, ref="FETCH_HEAD"):
        return self.merge_by.get(p.name, _R(0))

    def head_commit(self, p):
        seq = self.heads_by.setdefault(p.name, ["a1b2c3d4e", "a1b2c3d4e"])
        return seq.pop(0) if len(seq) > 1 else seq[0]


class PullServiceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)
        self.root = make_workspace(self.home, repos=("odoo", "documentation"))
        make_worktree(self.root, "19.0", version="19.0", repos=("documentation",))
        self.workspace = Workspace(root=self.root, config=None)
        self.worktree = Worktree(name="19.0", path=self.root / "19.0")
        self.git = FakeGit()

    def pull(self, worktree=None):
        return PullService(self.git).pull(self.workspace, worktree or self.worktree)

    def by_repo(self, result):
        return {o.repo: o for o in result.outcomes}

    def test_up_to_date_when_head_unchanged(self):
        out = self.by_repo(self.pull())
        self.assertEqual(set(out), {"odoo", "documentation"})
        self.assertEqual(out["odoo"].status, UP_TO_DATE)

    def test_advanced_reports_the_range(self):
        self.git.heads_by["odoo"] = ["oldsha111x", "newsha222y"]
        out = self.by_repo(self.pull())
        self.assertEqual(out["odoo"].status, ADVANCED)
        self.assertEqual(out["odoo"].detail, "oldsha111..newsha222")

    def test_diverged_is_skipped_with_rebase_guidance(self):
        self.git.merge_by["odoo"] = _R(1)
        out = self.by_repo(self.pull())["odoo"]
        self.assertEqual(out.status, SKIPPED)
        self.assertIn("diverged from origin/19.0", out.detail)
        self.assertIn("pull --rebase origin 19.0", out.detail)

    def test_feature_branch_without_version_is_skipped(self):
        self.git.branch = "customer-b"
        out = self.by_repo(self.pull())["odoo"]
        self.assertEqual(out.status, SKIPPED)
        self.assertIn("tracks no version", out.detail)

    def test_dirty_checkout_is_skipped(self):
        self.git.dirty_names = {"odoo"}
        out = self.by_repo(self.pull())["odoo"]
        self.assertEqual(out.status, SKIPPED)
        self.assertIn("uncommitted changes", out.detail)

    def test_missing_origin_branch_is_skipped(self):
        self.git.fetch_by["odoo"] = _R(1, stderr="fatal: couldn't find remote ref 19.0")
        out = self.by_repo(self.pull())["odoo"]
        self.assertEqual(out.status, SKIPPED)
        self.assertIn("origin has no '19.0' branch", out.detail)

    def test_offline_fetch_is_skipped(self):
        self.git.fetch_by["odoo"] = _R(1, stderr="could not resolve host github.com")
        out = self.by_repo(self.pull())["odoo"]
        self.assertEqual(out.status, SKIPPED)
        self.assertIn("offline", out.detail)

    def test_detached_head_is_skipped(self):
        self.git.branch_by["odoo"] = None
        out = self.by_repo(self.pull())["odoo"]
        self.assertEqual(out.status, SKIPPED)
        self.assertIn("detached", out.detail)

    def test_plain_directories_are_ignored(self):
        (self.root / "19.0" / "notes").mkdir()
        out = self.by_repo(self.pull())
        self.assertNotIn("notes", out)

    def test_linked_checkout_records_its_source(self):
        make_worktree(self.root, "19.0-link", linked_from="19.0", repos=())
        linked = Worktree(name="19.0-link", path=self.root / "19.0-link")
        out = self.by_repo(self.pull(linked))
        self.assertIn("odoo", out)
        self.assertEqual(out["odoo"].linked_from, "19.0")


if __name__ == "__main__":
    unittest.main()
