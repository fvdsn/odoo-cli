import os
import tempfile
import unittest
from pathlib import Path

from odoo_cli.cli._click import testing
from odoo_cli.cli.context import CliContext, Services
from odoo_cli.cli.main import cli
from odoo_cli.core.venvs import VenvService
from tests.fixtures.process import FakeProcessRunner
from tests.fixtures.workspace import make_env, make_workspace, make_worktree


class RepoWorktreeTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name).resolve()
        self.env = make_env(self.home)
        self.root = make_workspace(self.home)
        self.runner = FakeProcessRunner()
        self.cli_runner = testing.CliRunner()
        self.tools = {"uv": "/usr/bin/uv"}
        self.runner.expect("git", stdout="ok")
        self.runner.expect(
            "git", "clone",
            effect=lambda call: Path(call[-1]).mkdir(parents=True, exist_ok=True),
        )
        self.runner.expect("uv", stdout="")

    def invoke(self, *args):
        services = Services(process=self.runner, env=self.env)
        services.venvs = VenvService(self.runner, which=self.tools.get)
        return self.cli_runner.invoke(cli, list(args), obj=CliContext(services=services))

    def repos(self):
        return self.root / ".repositories"


class TestRepoAdd(RepoWorktreeTestCase):
    def test_add_clones(self):
        result = self.invoke(
            "repo", "add", "customer-a-addons", "git@example.com:a.git"
        )
        self.assertEqual(result.exit_code, 0, result.output)
        clone = next(c for c in self.runner.calls if c[1] == "clone")
        self.assertIn("git@example.com:a.git", clone)
        self.assertIn("added repository customer-a-addons", result.output)

    def test_add_builtin_redirects_to_enable(self):
        result = self.invoke("repo", "add", "enterprise", "git@x:e.git")
        self.assertEqual(result.exit_code, 1)
        self.assertIn("repo enable", result.exception.hint)


class TestRepoEnable(RepoWorktreeTestCase):
    def setUp(self):
        super().setUp()
        make_worktree(self.root, "19.0", version="19.0")
        make_worktree(self.root, "17.0", version="17.0")

    def test_enable_adds_to_compatible_worktrees(self):
        repo = str(self.repos() / "enterprise.git")
        self.runner.expect("git", "--version", stdout="git version 2.54.0\n")
        self.runner.expect(
            "git", "-C", repo, "rev-parse", "--verify", "--quiet",
            "refs/heads/17.0", returncode=1,
        )
        result = self.invoke("repo", "enable", "enterprise")
        self.assertEqual(result.exit_code, 0, result.output)
        clone = next(c for c in self.runner.calls if c[1] == "clone")
        self.assertIn("git@github.com:odoo/enterprise.git", clone)
        self.assertIn("Cloning enterprise (blobless)...", result.output)
        self.assertIn("added to: 19.0", result.output)
        self.assertIn("skipped 17.0: no branch '17.0'", result.output)

    def test_enable_fetch_output_has_no_clone_mode(self):
        (self.repos() / "enterprise.git").mkdir()
        result = self.invoke("repo", "enable", "enterprise", "--future-only")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Fetching enterprise...", result.output)
        self.assertNotIn("Fetching enterprise (", result.output)

    def test_future_only(self):
        result = self.invoke("repo", "enable", "enterprise", "--future-only")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("untouched", result.output)
        self.assertFalse(
            any("worktree" in c for c in self.runner.calls),
            "no worktree should be modified",
        )

    def test_to_scopes_worktrees(self):
        result = self.invoke("repo", "enable", "enterprise", "--to", "19.0")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("added to: 19.0", result.output)
        self.assertNotIn("17.0", result.output.split("added to: 19.0")[1])

    def test_unknown_optional_repo(self):
        result = self.invoke("repo", "enable", "nonsense")
        self.assertEqual(result.exit_code, 1)
        self.assertIn("enterprise", result.exception.hint)


class TestWorktreeCreate(RepoWorktreeTestCase):
    def worktree_effect(self, version):
        def effect(call):
            dest = Path(call[5] if call[5] != "-b" else call[7])
            dest.mkdir(parents=True, exist_ok=True)
            if dest.name == "odoo":
                from tests.fixtures.workspace import version_release_py

                (dest / "odoo").mkdir(exist_ok=True)
                (dest / "odoo" / "release.py").write_text(
                    version_release_py(version)
                )

        return effect

    def test_single_argument_is_name_and_version(self):
        for repo in ("odoo.git", "documentation.git"):
            self.runner.expect(
                "git", "-C", str(self.repos() / repo), "worktree", "add",
                effect=self.worktree_effect("19.0"),
            )
        result = self.invoke("worktree", "create", "19.0")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("worktree 19.0 ready", result.output)
        self.assertTrue((self.root / "19.0" / "odoo").is_dir())

    def test_single_argument_must_be_a_version(self):
        repo = str(self.repos() / "odoo.git")
        self.runner.expect("git", "-C", repo, "rev-parse", returncode=1)
        # the repo itself is healthy; only the branch lookup fails
        self.runner.expect(
            "git", "-C", repo, "rev-parse", "--verify", "--quiet", "HEAD",
            stdout="abc123\n",
        )
        result = self.invoke("worktree", "create", "my-feature")
        self.assertEqual(result.exit_code, 1)
        self.assertIn("NAME VERSION", result.exception.hint)

    def test_linked_create_with_addon(self):
        make_worktree(self.root, "19.0", version="19.0")
        (self.repos() / "customer-a-addons.git").mkdir()
        result = self.invoke(
            "worktree", "create", "customer-a", "19.0",
            "--linked", "--addon", "customer-a-addons",
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("linked odoo from 19.0", result.output)
        self.assertIn("checked out customer-a-addons", result.output)
        self.assertEqual(
            os.readlink(self.root / "customer-a" / "odoo"), "../19.0/odoo"
        )

    def test_addon_requires_linked(self):
        result = self.invoke(
            "worktree", "create", "x", "19.0", "--addon", "a"
        )
        self.assertEqual(result.exit_code, 2)

    def test_linked_requires_a_source(self):
        result = self.invoke("worktree", "create", "customer-a", "--linked")
        self.assertEqual(result.exit_code, 2)
        self.assertIn("NAME SOURCE --linked", result.output)

    def test_linked_source_must_not_be_linked(self):
        make_worktree(self.root, "19.0", version="19.0")
        make_worktree(self.root, "customer-a", linked_from="19.0")
        result = self.invoke(
            "worktree", "create", "customer-b", "customer-a", "--linked"
        )
        self.assertEqual(result.exit_code, 1)
        self.assertIn("link from '19.0' instead", result.exception.hint)

    def test_worktree_source_without_linked_hints_at_linked(self):
        make_worktree(self.root, "fix-pos", version="19.0")
        repo = str(self.repos() / "odoo.git")
        self.runner.expect("git", "-C", repo, "rev-parse", returncode=1)
        # the repo itself is healthy; only the branch lookup fails
        self.runner.expect(
            "git", "-C", repo, "rev-parse", "--verify", "--quiet", "HEAD",
            stdout="abc123\n",
        )
        result = self.invoke("worktree", "create", "hotfix", "fix-pos")
        self.assertEqual(result.exit_code, 1)
        self.assertIn("--linked", result.exception.hint)
        self.assertIn("not supported yet", result.exception.hint)


class TestVenvCommand(RepoWorktreeTestCase):
    def test_rebuild(self):
        make_worktree(self.root, "19.0", version="19.0")
        result = self.invoke("venv")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("venv ready", result.output)
        self.assertTrue(
            any(c[:2] == ("uv", "venv") for c in self.runner.calls)
        )
