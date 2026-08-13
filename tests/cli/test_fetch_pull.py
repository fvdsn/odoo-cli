import tempfile
import unittest
from pathlib import Path

from odoo_cli.cli._click import testing
from odoo_cli.cli.context import CliContext, Services
from odoo_cli.cli.main import cli
from tests.fixtures.process import FakeProcessRunner
from tests.fixtures.workspace import make_env, make_workspace, make_worktree


class FetchPullTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name).resolve()
        self.env = make_env(self.home)
        self.root = make_workspace(self.home, repos=("odoo", "documentation"))
        self.runner = FakeProcessRunner()
        self.runner.expect("git", stdout="ok")  # broad default: success
        self.cli_runner = testing.CliRunner()

    def invoke(self, *args):
        services = Services(process=self.runner, env=self.env)
        return self.cli_runner.invoke(
            cli, list(args), obj=CliContext(services=services)
        )


class TestFetch(FetchPullTestCase):
    def test_fetches_all_repos(self):
        result = self.invoke("fetch")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("fetched", result.output)
        self.assertIn("odoo", result.output)
        self.assertIn("documentation", result.output)
        # an actual bare-repo fetch ran for each
        fetches = [c for c in self.runner.calls if c[:2] == ("git", "-C") and "fetch" in c]
        self.assertEqual(len(fetches), 2)

    def test_fetches_only_named_repo(self):
        result = self.invoke("fetch", "odoo")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("fetched odoo", result.output)
        self.assertNotIn("documentation", result.output)

    def test_unknown_repo_is_skipped(self):
        result = self.invoke("fetch", "nope")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("skipped nope: no such repository", result.output)

    def test_incomplete_repo_is_skipped(self):
        # documentation has no resolvable HEAD -> incomplete clone
        doc = self.root / ".repositories" / "documentation.git"
        self.runner.expect("git", "-C", str(doc), "rev-parse", returncode=1)
        result = self.invoke("fetch")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("skipped documentation: incomplete clone", result.output)
        self.assertIn("fetched odoo", result.output)


class TestPull(FetchPullTestCase):
    def setUp(self):
        super().setUp()
        make_worktree(self.root, "19.0", version="19.0", repos=("documentation",))
        for repo in ("odoo", "documentation"):
            p = self.root / "19.0" / repo
            self.runner.expect("git", "-C", str(p), "symbolic-ref", stdout="19.0\n")
            self.runner.expect("git", "-C", str(p), "status", "--porcelain", stdout="")

    def test_pull_up_to_date(self):
        result = self.invoke("pull")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Pulling worktree 19.0", result.output)
        self.assertIn("already up to date", result.output)
        self.assertIn("up to date", result.output)
        # each checkout fetched its base by name, then ff-merged
        self.assertTrue(
            any(c[-3:] == ("fetch", "origin", "19.0") for c in self.runner.calls)
        )

    def set_ahead(self, checkout, old="oldsha111x", new="newsha222y", related=True):
        """Script HEAD/FETCH_HEAD shas and their ancestry for a checkout."""
        self.runner.expect(
            "git", "-C", str(checkout), "rev-parse", "HEAD", stdout=f"{old}\n"
        )
        self.runner.expect(
            "git", "-C", str(checkout),
            "rev-parse", "--verify", "--quiet", "FETCH_HEAD", stdout=f"{new}\n",
        )
        self.runner.expect(
            "git", "-C", str(checkout), "merge-base", "--is-ancestor",
            returncode=0 if related else 1,
        )
        if related:
            # HEAD is behind FETCH_HEAD, not the reverse
            self.runner.expect(
                "git", "-C", str(checkout),
                "merge-base", "--is-ancestor", new, old, returncode=1,
            )

    def test_pull_advanced_streams_the_merge(self):
        odoo = self.root / "19.0" / "odoo"
        self.set_ahead(odoo)
        result = self.invoke("pull")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("odoo: oldsha111..newsha222", result.output)
        # the ff merge ran attached to the terminal, with the diffstat off
        self.assertTrue(
            any(
                c[-4:] == ("merge", "--ff-only", "--no-stat", "FETCH_HEAD")
                for c in self.runner.stream_calls
            ),
            self.runner.stream_calls,
        )

    def test_pull_json_keeps_output_captured(self):
        odoo = self.root / "19.0" / "odoo"
        self.set_ahead(odoo)
        result = self.invoke("pull", "--json")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn('"advanced"', result.output)
        self.assertEqual(self.runner.stream_calls, [])

    def test_pull_skips_diverged_with_guidance(self):
        odoo = self.root / "19.0" / "odoo"
        self.set_ahead(odoo, new="forksha333z", related=False)
        result = self.invoke("pull")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("skipped odoo: diverged from origin/19.0", result.output)
        self.assertIn("pull --rebase origin 19.0", result.output)
        # documentation still pulled (up to date); only odoo was skipped
        self.assertIn("1 skipped", result.output)
        self.assertIn("already up to date", result.output)


if __name__ == "__main__":
    unittest.main()
