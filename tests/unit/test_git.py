import unittest

from odoo_cli.util.git import Git
from tests.fixtures.process import FakeProcessRunner


class TestGitVersion(unittest.TestCase):
    def setUp(self):
        self.runner = FakeProcessRunner()
        self.git = Git(self.runner)

    def test_parses_plain_version(self):
        self.runner.expect("git", "--version", stdout="git version 2.54.0\n")

        self.assertEqual(self.git.version(), (2, 54, 0))

    def test_parses_apple_version_suffix(self):
        self.runner.expect(
            "git",
            "--version",
            stdout="git version 2.39.1 (Apple Git-143)\n",
        )

        self.assertEqual(self.git.version(), (2, 39, 1))

    def test_reliable_blobless_requires_git_2_40(self):
        self.runner.expect("git", "--version", stdout="git version 2.39.1\n")

        self.assertFalse(self.git.supports_reliable_blobless_clone())

    def test_reliable_blobless_accepts_git_2_40(self):
        self.runner.expect("git", "--version", stdout="git version 2.40.0\n")

        self.assertTrue(self.git.supports_reliable_blobless_clone())


class TestFetch(unittest.TestCase):
    def setUp(self):
        self.runner = FakeProcessRunner()
        self.git = Git(self.runner)

    def test_fetch_builds_negative_refspecs(self):
        self.runner.expect("git", stdout="")
        self.git.fetch("/repos/odoo.git", exclude_branches=["19.0", "fix-pos"])
        self.assertEqual(
            self.runner.calls[0],
            (
                "git", "-C", "/repos/odoo.git", "fetch", "origin",
                "+refs/heads/*:refs/heads/*",
                "^refs/heads/19.0", "^refs/heads/fix-pos",
            ),
        )

    def test_worktree_branches_parses_porcelain(self):
        self.runner.expect(
            "git", stdout=(
                "worktree /repos/odoo.git\nbare\n\n"
                "worktree /ws/19.0/odoo\nHEAD abc\nbranch refs/heads/19.0\n\n"
                "worktree /ws/detached/odoo\nHEAD def\ndetached\n"
            ),
        )
        self.assertEqual(
            self.git.worktree_branches("/repos/odoo.git"), ["19.0"]
        )
