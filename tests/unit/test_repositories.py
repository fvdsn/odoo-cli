import tempfile
import unittest
from pathlib import Path

from odoo_cli.core.errors import (
    InvalidWorktreeName,
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
        self.service.add(
            self.workspace, "customer-a-addons", "git@example.com:a.git"
        )
        self.assertEqual(
            self.runner.calls[0],
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
        self.service.add(
            self.workspace, "customer-a-addons", "git@example.com:a.git", full=True
        )
        self.assertNotIn("--filter=blob:none", self.runner.calls[0])

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
