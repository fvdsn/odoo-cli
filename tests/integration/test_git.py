"""util.git against real local repositories (no network)."""

import shutil
import tempfile
import unittest
from pathlib import Path

from odoo_cli.util.git import Git
from odoo_cli.util.process import ProcessRunner


@unittest.skipUnless(shutil.which("git"), "git not installed")
class TestGitIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        base = Path(cls._tmp.name)
        cls.runner = ProcessRunner()
        cls.git = Git(cls.runner)
        cls.env = {
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
        }

        cls.source = base / "source"
        cls.source.mkdir()

        def g(*args, cwd=cls.source):
            cls.runner.run(["git", *args], cwd=cwd, extra_env=cls.env)

        g("init", "-q", "-b", "19.0")
        (cls.source / "README").write_text("hello\n")
        g("add", "README")
        g("commit", "-qm", "initial")
        g("branch", "18.0")

        cls.bare = base / "repo.git"
        cls.git.clone_bare(str(cls.source), cls.bare, blobless=False)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_remote_url(self):
        self.assertEqual(self.git.remote_url(self.bare), str(self.source))

    def test_branch_exists(self):
        self.assertTrue(self.git.branch_exists(self.bare, "19.0"))
        self.assertFalse(self.git.branch_exists(self.bare, "99.0"))

    def test_list_branches(self):
        self.assertEqual(
            sorted(self.git.list_branches(self.bare)), ["18.0", "19.0"]
        )

    def test_fetch_with_worktrees_updates_origin_and_keeps_local_branches(self):
        """P1 regression: the workspace model exactly — a bare repo with a
        checked-out version branch and a local-only feature branch. The
        fetch must succeed (git refuses to fetch into checked-out branches),
        update non-checked-out origin branches, and delete nothing."""
        base = Path(self._tmp.name) / "fetch-scenario"
        base.mkdir()
        bare = base / "central.git"
        self.git.clone_bare(str(self.source), bare, blobless=False)
        wt = base / "19.0" / "odoo"
        wt.parent.mkdir()
        self.git.worktree_add(bare, wt, "19.0")
        # a worktree feature branch whose worktree was removed: the branch
        # stays (requirements.md: reused, never reset) and must survive
        self.runner.run(
            ["git", "-C", bare, "branch", "fix-pos", "19.0"], extra_env=self.env
        )
        # origin moves forward: a new commit, and 18.0 (not checked out in
        # the bare repo's worktrees) advances to it
        self.runner.run(
            ["git", "-C", self.source, "commit", "-q", "--allow-empty", "-m", "more"],
            extra_env=self.env,
        )
        self.runner.run(
            ["git", "-C", self.source, "branch", "-f", "18.0"], extra_env=self.env
        )

        def rev(repo, ref):
            result = self.runner.run(["git", "-C", repo, "rev-parse", ref])
            return result.stdout.strip()

        old_19 = rev(bare, "19.0")
        checked_out = self.git.worktree_branches(bare)
        self.assertEqual(checked_out, ["19.0"])
        self.git.fetch(bare, exclude_branches=checked_out)

        self.assertTrue(self.git.branch_exists(bare, "fix-pos"))
        self.assertEqual(rev(bare, "18.0"), rev(self.source, "18.0"))
        self.assertEqual(rev(bare, "19.0"), old_19)  # left to its worktree

    def test_worktree_add_and_new_branch(self):
        base = Path(self._tmp.name)
        dest = base / "wt" / "odoo"
        dest.parent.mkdir(exist_ok=True)
        self.git.worktree_add(self.bare, dest, "18.0")
        self.assertTrue((dest / "README").is_file())

        dest2 = base / "wt2" / "odoo"
        dest2.parent.mkdir(exist_ok=True)
        self.git.worktree_add(self.bare, dest2, "feature", new_branch_from="19.0")
        self.assertTrue((dest2 / "README").is_file())
        self.assertTrue(self.git.branch_exists(self.bare, "feature"))
