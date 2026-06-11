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
        runner = ProcessRunner()
        cls.git = Git(runner)

        cls.source = base / "source"
        cls.source.mkdir()
        env = {
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
        }

        def g(*args, cwd=cls.source):
            runner.run(["git", *args], cwd=cwd, extra_env=env)

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
