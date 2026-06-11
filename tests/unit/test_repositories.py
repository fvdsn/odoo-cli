import tempfile
import unittest
from pathlib import Path

from odoo_cli.core.errors import (
    InvalidWorktreeName,
    OdooCliError,
    RepositoryExists,
    RepositoryNotFound,
    VersionNotFound,
)
from odoo_cli.core.models import Workspace
from odoo_cli.core.repositories import RepositoryService
from odoo_cli.util.git import Git
from tests.fixtures.process import FakeProcessRunner
from tests.fixtures.workspace import make_workspace


class RepositoryTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)
        self.root = make_workspace(self.home)
        self.workspace = Workspace(root=self.root, config=None)
        self.runner = FakeProcessRunner()
        self.service = RepositoryService(Git(self.runner))

    def allow_git_version(self, version="2.54.0"):
        self.runner.expect("git", "--version", stdout=f"git version {version}\n")


class TestListing(RepositoryTestCase):
    def test_list_reads_directory(self):
        self.runner.expect("git", stdout="https://example.com/r.git\n")
        repos = self.service.list(self.workspace)
        self.assertEqual([r.name for r in repos], ["documentation", "odoo"])

    def test_missing_origin_surfaces_none(self):
        self.runner.expect("git", returncode=2)
        spec = self.service.get(self.workspace, "odoo")
        self.assertIsNone(spec.url)

    def test_get_unknown_repository(self):
        with self.assertRaises(RepositoryNotFound):
            self.service.get(self.workspace, "customer-a-addons")


class TestAdd(RepositoryTestCase):
    def test_add_clones_blobless_by_default(self):
        self.runner.expect("git", stdout="")
        self.allow_git_version()
        self.service.add(
            self.workspace, "customer-a-addons", "git@example.com:a.git"
        )
        clone = next(c for c in self.runner.calls if c[:2] == ("git", "clone"))
        self.assertEqual(
            clone,
            (
                "git",
                "clone",
                "--bare",
                "--filter=blob:none",
                "git@example.com:a.git",
                str(self.root / ".repositories" / "customer-a-addons.git"),
            ),
        )

    def test_add_full_clone(self):
        self.runner.expect("git", stdout="")
        self.allow_git_version()
        self.service.add(
            self.workspace, "customer-a-addons", "git@example.com:a.git", full=True
        )
        clone = next(c for c in self.runner.calls if c[:2] == ("git", "clone"))
        self.assertNotIn("--filter=blob:none", clone)

    def test_add_uses_full_clone_with_old_git(self):
        self.runner.expect("git", stdout="")
        self.allow_git_version("2.39.1")
        self.service.add(
            self.workspace, "customer-a-addons", "git@example.com:a.git"
        )
        clone = next(c for c in self.runner.calls if c[:2] == ("git", "clone"))
        self.assertNotIn("--filter=blob:none", clone)

    def test_add_rejects_builtin_names(self):
        with self.assertRaises(RepositoryExists) as cm:
            self.service.add(self.workspace, "enterprise", "git@example.com:e.git")
        self.assertIn("repo enable", cm.exception.hint)

    def test_add_rejects_existing(self):
        with self.assertRaises(RepositoryExists):
            self.service.add(self.workspace, "odoo", "git@example.com:o.git")

    def test_add_rejects_invalid_names(self):
        for bad in ("", "a/b", "a b", ".repositories"):
            with self.assertRaises(InvalidWorktreeName):
                self.service.add(self.workspace, bad, "git@example.com:x.git")


class TestCloneOrFetch(RepositoryTestCase):
    def test_full_replaces_existing_partial_clone_without_worktrees(self):
        old_marker = self.root / ".repositories" / "odoo.git" / "old"
        old_marker.write_text("partial\n")

        def clone_effect(call):
            Path(call[-1]).mkdir(parents=True, exist_ok=True)

        self.runner.expect("git", "clone", effect=clone_effect)
        self.runner.expect(
            "git",
            "-C",
            str(self.root / ".repositories" / "odoo.git"),
            "worktree",
            "list",
            stdout=f"worktree {self.root / '.repositories' / 'odoo.git'}\nbare\n",
        )
        self.runner.expect(
            "git",
            "-C",
            str(self.root / ".repositories" / "odoo.git"),
            "config",
            "--get",
            "remote.origin.promisor",
            stdout="true\n",
        )
        self.runner.expect(
            "git",
            "-C",
            str(self.root / ".repositories" / "odoo.git"),
            "remote",
            stdout="https://github.com/odoo/odoo.git\n",
        )
        self.allow_git_version()

        self.service.clone_or_fetch(self.workspace, "odoo", full=True)

        clone = next(c for c in self.runner.calls if c[:2] == ("git", "clone"))
        self.assertNotIn("--filter=blob:none", clone)
        self.assertFalse(old_marker.exists())
        self.assertTrue((self.root / ".repositories" / "odoo.git").is_dir())

    def test_full_refuses_to_replace_repository_with_attached_worktrees(self):
        self.runner.expect(
            "git",
            "-C",
            str(self.root / ".repositories" / "odoo.git"),
            "worktree",
            "list",
            stdout=(
                f"worktree {self.root / '.repositories' / 'odoo.git'}\n"
                "bare\n\n"
                f"worktree {self.root / '19.0' / 'odoo'}\n"
                "HEAD abc123\n"
            ),
        )
        self.runner.expect(
            "git",
            "-C",
            str(self.root / ".repositories" / "odoo.git"),
            "config",
            "--get",
            "remote.origin.promisor",
            stdout="true\n",
        )
        self.runner.expect(
            "git",
            "-C",
            str(self.root / ".repositories" / "odoo.git"),
            "remote",
            stdout="https://github.com/odoo/odoo.git\n",
        )
        self.allow_git_version()

        with self.assertRaises(OdooCliError):
            self.service.clone_or_fetch(self.workspace, "odoo", full=True)

    def test_old_git_replaces_existing_partial_clone_with_full_clone(self):
        def clone_effect(call):
            Path(call[-1]).mkdir(parents=True, exist_ok=True)

        self.runner.expect("git", "clone", effect=clone_effect)
        self.runner.expect(
            "git",
            "-C",
            str(self.root / ".repositories" / "odoo.git"),
            "worktree",
            "list",
            stdout=f"worktree {self.root / '.repositories' / 'odoo.git'}\nbare\n",
        )
        self.runner.expect(
            "git",
            "-C",
            str(self.root / ".repositories" / "odoo.git"),
            "config",
            "--get",
            "remote.origin.promisor",
            stdout="true\n",
        )
        self.runner.expect(
            "git",
            "-C",
            str(self.root / ".repositories" / "odoo.git"),
            "remote",
            stdout="https://github.com/odoo/odoo.git\n",
        )
        self.allow_git_version("2.39.1")

        self.service.clone_or_fetch(self.workspace, "odoo")

        clone = next(c for c in self.runner.calls if c[:2] == ("git", "clone"))
        self.assertNotIn("--filter=blob:none", clone)


class TestVersions(RepositoryTestCase):
    def test_require_version(self):
        self.runner.expect("git", returncode=1)
        repo = self.service.get(self.workspace, "odoo")
        with self.assertRaises(VersionNotFound):
            self.service.require_version(repo, "19.0")

    def test_latest_stable_version(self):
        self.runner.expect("git", stdout="")  # remote_url fallback
        self.runner.expect(
            "git",
            "-C",
            str(self.root / ".repositories" / "odoo.git"),
            "for-each-ref",
            stdout="16.0\n17.0\n18.0\n19.0\nmaster\nsaas-19.4\n9.0\n",
        )
        repo = self.service.get(self.workspace, "odoo")
        self.assertEqual(self.service.latest_stable_version(repo), "19.0")
