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
    """Scripted by checkout dir name (odoo, documentation, …). Ancestry is a
    linear `history_by` list of shas (oldest first); shas absent from it are
    unrelated (diverged)."""

    def __init__(self):
        self.branch = "19.0"
        self.branch_by: dict[str, str | None] = {}
        self.dirty_names: set[str] = set()
        self.fetch_by: dict[str, _R] = {}
        self.merge_by: dict[str, _R] = {}
        self.head_by: dict[str, str] = {}
        self.fetch_head_by: dict[str, str] = {}
        self.history_by: dict[str, list[str]] = {}
        self.stream_rc_by: dict[str, int] = {}
        self.streamed: list[str] = []

    def current_branch(self, p):
        return self.branch_by.get(p.name, self.branch)

    def is_dirty(self, p):
        return p.name in self.dirty_names

    def fetch_branch(self, p, base):
        return self.fetch_by.get(p.name, _R(0))

    def merge_ff_only(self, p, ref="FETCH_HEAD"):
        return self.merge_by.get(p.name, _R(0))

    def merge_ff_only_streamed(self, p, ref="FETCH_HEAD"):
        self.streamed.append(p.name)
        return self.stream_rc_by.get(p.name, 0)

    def head_commit(self, p):
        return self.head_by.get(p.name, "a1b2c3d4e")

    def commit_of(self, p, ref):
        return self.fetch_head_by.get(p.name, self.head_commit(p))

    def is_ancestor(self, p, ancestor, descendant):
        history = self.history_by.get(p.name, [])
        if ancestor not in history or descendant not in history:
            return False
        return history.index(ancestor) <= history.index(descendant)


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

    def pull(self, worktree=None, stream=False):
        return PullService(self.git).pull(
            self.workspace, worktree or self.worktree, stream=stream
        )

    def by_repo(self, result):
        return {o.repo: o for o in result.outcomes}

    def set_behind(self, name, old="oldsha111x", new="newsha222y"):
        """Script a checkout whose FETCH_HEAD is strictly ahead of HEAD."""
        self.git.head_by[name] = old
        self.git.fetch_head_by[name] = new
        self.git.history_by[name] = [old, new]

    def test_up_to_date_when_head_unchanged(self):
        out = self.by_repo(self.pull())
        self.assertEqual(set(out), {"odoo", "documentation"})
        self.assertEqual(out["odoo"].status, UP_TO_DATE)

    def test_up_to_date_when_fetch_head_is_behind(self):
        self.set_behind("odoo", old="newsha222y", new="oldsha111x")
        self.git.history_by["odoo"] = ["oldsha111x", "newsha222y"]
        out = self.by_repo(self.pull())
        self.assertEqual(out["odoo"].status, UP_TO_DATE)

    def test_advanced_reports_the_range(self):
        self.set_behind("odoo")
        out = self.by_repo(self.pull())
        self.assertEqual(out["odoo"].status, ADVANCED)
        self.assertEqual(out["odoo"].detail, "oldsha111..newsha222")

    def test_streamed_merge_when_requested(self):
        self.set_behind("odoo")
        out = self.by_repo(self.pull(stream=True))
        self.assertEqual(out["odoo"].status, ADVANCED)
        # only the checkout that actually fast-forwards streams a merge
        self.assertEqual(self.git.streamed, ["odoo"])

    def test_interrupted_merge_points_at_recovery(self):
        self.set_behind("odoo")
        self.git.stream_rc_by["odoo"] = 130
        out = self.by_repo(self.pull(stream=True))["odoo"]
        self.assertEqual(out.status, SKIPPED)
        self.assertIn("did not finish", out.detail)
        self.assertIn("reset --hard FETCH_HEAD", out.detail)

    def test_diverged_is_skipped_with_rebase_guidance(self):
        self.git.head_by["odoo"] = "oldsha111x"
        self.git.fetch_head_by["odoo"] = "forksha333z"
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
