import tempfile
import unittest
from pathlib import Path

from odoo_cli.cli._click import testing
from odoo_cli.cli.context import CliContext, Services
from odoo_cli.cli.main import cli
from odoo_cli.core.odoo_conf import OdooConf
from odoo_cli.core.postgres import PostgresService
from odoo_cli.core.venvs import VenvService
from tests.fixtures.process import FakeProcessRunner
from tests.fixtures.workspace import make_env, version_release_py


class InitCommandTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name).resolve()
        self.env = make_env(self.home)
        self.root = self.home / "odoo"
        self.runner = FakeProcessRunner()
        self.tools = {
            "psql": "/usr/bin/psql",
            "runuser": "/usr/sbin/runuser",
            "uv": "/usr/bin/uv",
            "python3.13": "/usr/bin/python3.13",
        }
        self.sockets = self.home / "sockets"
        self.cli_runner = testing.CliRunner()

    def context(self) -> CliContext:
        services = Services(process=self.runner, env=self.env)
        services.postgres = PostgresService(
            self.runner,
            which=self.tools.get,
            platform="linux",
            geteuid=lambda: 0,
            current_user=lambda: "dev",
            socket_dirs=(self.sockets,),
            environ={},
        )
        services.venvs = VenvService(self.runner, which=self.tools.get)
        return CliContext(services=services)

    def invoke(self, *args):
        return self.cli_runner.invoke(cli, list(args), obj=self.context())

    def script_happy_path(self, version="19.0"):
        def clone_effect(call):
            Path(call[-1]).mkdir(parents=True, exist_ok=True)

        def worktree_effect(call):
            dest = Path(call[5])
            dest.mkdir(parents=True, exist_ok=True)
            if dest.name == "odoo":
                (dest / "odoo").mkdir()
                (dest / "odoo" / "release.py").write_text(
                    version_release_py(version)
                )

        # broad fallback first: later, more specific registrations win
        self.runner.expect("git", stdout="")  # remote_url, rev-parse, fetch
        self.runner.expect("git", "--version", stdout="git version 2.54.0\n")
        self.runner.expect("git", "clone", effect=clone_effect)
        repos = self.root / ".repositories"
        for repo in ("odoo.git", "documentation.git"):
            self.runner.expect(
                "git", "-C", str(repos / repo), "remote",
                stdout=f"https://github.com/odoo/{repo}\n",
            )
        self.runner.expect(
            "git", "-C", str(repos / "odoo.git"), "for-each-ref",
            stdout="17.0\n18.0\n19.0\nmaster\n",
        )
        for repo in ("odoo.git", "documentation.git"):
            self.runner.expect(
                "git", "-C", str(repos / repo), "worktree", "add",
                effect=worktree_effect,
            )
        self.runner.expect("uv", stdout="")
        self.runner.expect("psql", stdout="1\n")


class TestInit(InitCommandTestCase):
    def test_bootstrap_default_version(self):
        self.script_happy_path()
        result = self.invoke("init")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertTrue((self.root / ".repositories" / "odoo.git").is_dir())
        self.assertTrue((self.root / "19.0" / "odoo").is_dir())
        self.assertIn("Next: cd", result.output)
        self.assertIn("odoo start", result.output)
        # default conf written
        conf = OdooConf.load(self.home / ".config" / "odoo" / "odoo.conf")
        self.assertEqual(conf.get("dev_mode"), "all")
        # blobless clone by default
        clone = next(c for c in self.runner.calls if c[:2] == ("git", "clone"))
        self.assertIn("--filter=blob:none", clone)
        self.assertIn("this can take a few minutes", result.output)
        # the download message names the destination workspace dir
        self.assertIn(f"Downloading the Odoo sources to {self.root}", result.output)

    def test_explicit_version(self):
        self.script_happy_path(version="18.0")
        result = self.invoke("init", "18.0")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertTrue((self.root / "18.0").is_dir())

    def test_full_clone_flag(self):
        self.script_happy_path()
        result = self.invoke("init", "--full")
        self.assertEqual(result.exit_code, 0, result.output)
        clone = next(c for c in self.runner.calls if c[:2] == ("git", "clone"))
        self.assertNotIn("--filter=blob:none", clone)
        self.assertIn("this can take an hour", result.output)

    def test_old_git_falls_back_to_full_clone_and_says_so(self):
        self.script_happy_path()
        # registered last, wins over script_happy_path's 2.54
        self.runner.expect("git", "--version", stdout="git version 2.34.1\n")
        result = self.invoke("init")
        self.assertEqual(result.exit_code, 0, result.output)
        clone = next(c for c in self.runner.calls if c[:2] == ("git", "clone"))
        self.assertNotIn("--filter=blob:none", clone)
        self.assertIn("unreliable blobless clones", result.output)
        self.assertIn("this can take an hour", result.output)

    def test_no_demo_data_flag(self):
        self.script_happy_path()
        result = self.invoke("init", "--no-demo-data")
        self.assertEqual(result.exit_code, 0, result.output)
        conf = OdooConf.load(self.home / ".config" / "odoo" / "odoo.conf")
        self.assertEqual(conf.get("without_demo"), "True")

    def test_missing_postgres_installs_before_cloning(self):
        del self.tools["psql"]
        self.tools["apt-get"] = "/usr/bin/apt-get"
        self.tools["service"] = "/usr/sbin/service"

        def install_effect(call):
            self.tools["psql"] = "/usr/bin/psql"

        self.runner.expect_stream(
            "env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "update"
        )
        self.runner.expect_stream(
            "env", "DEBIAN_FRONTEND=noninteractive", "apt-get",
            "install", "-y", "postgresql", effect=install_effect
        )
        self.runner.expect_stream("service", "postgresql", "start")
        self.runner.expect("runuser", "-u", "postgres", "--", "createuser")
        self.script_happy_path()

        result = self.invoke("init")

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("installing with apt-get", result.output)
        self.assertEqual(
            self.runner.stream_calls[0],
            ("env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "update"),
        )
        self.assertEqual(
            self.runner.stream_calls[1],
            (
                "env", "DEBIAN_FRONTEND=noninteractive", "apt-get",
                "install", "-y", "postgresql",
            ),
        )
        self.assertTrue((self.root / ".repositories" / "odoo.git").is_dir())

    def test_missing_postgres_without_supported_manager_fails_before_cloning(self):
        del self.tools["psql"]

        result = self.invoke("init")

        self.assertEqual(result.exit_code, 1)
        self.assertEqual(self.runner.calls, [])  # nothing cloned
        self.assertEqual(self.runner.stream_calls, [])  # nothing installed

    def test_postgres_install_failure_fails_before_cloning(self):
        del self.tools["psql"]
        self.tools["apt-get"] = "/usr/bin/apt-get"
        self.runner.expect_stream(
            "env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "update",
            returncode=1,
        )

        result = self.invoke("init")

        self.assertEqual(result.exit_code, 1)
        self.assertIn("could not install PostgreSQL", result.exception.message)
        self.assertEqual(self.runner.calls, [])  # nothing cloned

    def test_existing_conf_is_never_modified(self):
        conf_path = self.home / ".config" / "odoo" / "odoo.conf"
        conf_path.parent.mkdir(parents=True)
        conf_path.write_text("[options]\ndb_user = me\n")
        self.script_happy_path()
        result = self.invoke("init")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(conf_path.read_text(), "[options]\ndb_user = me\n")
        self.assertIn("left untouched", result.output)

    def test_rerun_fetches_instead_of_cloning(self):
        self.script_happy_path()
        first = self.invoke("init")
        self.assertEqual(first.exit_code, 0, first.output)
        self.runner.calls.clear()
        result = self.invoke("init")
        self.assertEqual(result.exit_code, 0, result.output)
        fetches = [c for c in self.runner.calls if "fetch" in c]
        clones = [c for c in self.runner.calls if c[:2] == ("git", "clone")]
        self.assertEqual(len(fetches), 2)
        self.assertEqual(clones, [])
        self.assertIn("already exists", result.output)
        # nothing to clone: no duration heads-up
        self.assertNotIn("this can take", result.output)

    def test_rerun_offline_warns_and_continues(self):
        # a re-run on a complete workspace must not require the network:
        # everything needed is already local, fetch is only freshness
        self.script_happy_path()
        first = self.invoke("init")
        self.assertEqual(first.exit_code, 0, first.output)
        self.runner.calls.clear()
        for repo in ("odoo.git", "documentation.git"):
            self.runner.expect(
                "git", "-C", str(self.root / ".repositories" / repo), "fetch",
                returncode=128, stderr="fatal: unable to access remote\n",
            )

        result = self.invoke("init")

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("offline?", result.output)
        self.assertIn("Workspace ready", result.output)

    def test_rerun_repairs_incomplete_worktree(self):
        self.script_happy_path()
        incomplete = self.root / "19.0" / "odoo"
        incomplete.mkdir(parents=True)
        (incomplete / ".git").write_text("gitdir: broken\n")

        result = self.invoke("init")

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertTrue((self.root / "19.0" / "odoo" / "odoo" / "release.py").is_file())
        self.assertIn("recreating it", result.output)
        self.assertTrue(any(c[-2:] == ("worktree", "prune") for c in self.runner.calls))

    def test_blobless_promisor_checkout_failure_retries_with_full_clone(self):
        self.script_happy_path()
        prefix = (
            "git",
            "-C",
            str(self.root / ".repositories" / "odoo.git"),
            "worktree",
            "add",
        )

        def fail_once(call):
            # Remove this one-shot failure so the retry uses script_happy_path's
            # normal worktree side effect.
            for index, (registered, result, _effect) in enumerate(self.runner._scripts):
                if registered == prefix and result.returncode == 128:
                    self.runner._scripts.pop(index)
                    break
            Path(call[5]).mkdir(parents=True, exist_ok=True)

        self.runner.expect(
            *prefix,
            returncode=128,
            stderr="fatal: could not fetch abc from promisor remote\n",
            effect=fail_once,
        )

        result = self.invoke("init")

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("retrying with a full clone", result.output)

    def test_promisor_failure_reclones_the_repo_that_failed(self):
        """P2 regression: a promisor failure in documentation.git must
        reclone documentation, not odoo."""
        self.script_happy_path()
        doc_repo = self.root / ".repositories" / "documentation.git"
        prefix = ("git", "-C", str(doc_repo), "worktree", "add")

        def fail_once(call):
            for index, (registered, result, _effect) in enumerate(self.runner._scripts):
                if registered == prefix and result.returncode == 128:
                    self.runner._scripts.pop(index)
                    break
            Path(call[5]).mkdir(parents=True, exist_ok=True)

        self.runner.expect(
            *prefix,
            returncode=128,
            stderr="fatal: could not fetch abc from promisor remote\n",
            effect=fail_once,
        )

        result = self.invoke("init")

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("blobless documentation checkout failed", result.output)
        reclones = [
            c for c in self.runner.calls
            if c[:2] == ("git", "clone") and "documentation" in c[-1]
            and "--filter=blob:none" not in c
        ]
        self.assertTrue(reclones, "documentation was not recloned full")
        clones = [c for c in self.runner.calls if c[:2] == ("git", "clone")]
        self.assertGreaterEqual(len(clones), 3)
        self.assertNotIn("--filter=blob:none", clones[-1])

    def test_rerun_does_not_delete_unrecognized_existing_directory(self):
        self.script_happy_path()
        worktree = self.root / "19.0"
        worktree.mkdir(parents=True)
        (worktree / "notes.txt").write_text("keep me\n")

        result = self.invoke("init")

        self.assertEqual(result.exit_code, 1)
        self.assertTrue((worktree / "notes.txt").is_file())

    def test_connection_failure_warns_but_completes(self):
        self.script_happy_path()
        self.runner.expect("psql", returncode=2)
        result = self.invoke("init")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("could not connect to PostgreSQL", result.output)
        self.assertIn("Workspace ready", result.output)

    def test_connection_failure_adopts_detected_port(self):
        self.script_happy_path()
        self.sockets.mkdir(parents=True)
        (self.sockets / ".s.PGSQL.5433").touch()
        self.runner.expect("psql", returncode=2)
        self.runner.expect("psql", "--no-psqlrc", "-p", "5433", stdout="1\n")

        result = self.invoke("init")

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("PostgreSQL answers on port 5433", result.output)
        self.assertNotIn("could not connect", result.output)
        conf = OdooConf.load(self.home / ".config" / "odoo" / "odoo.conf")
        self.assertEqual(conf.get("db_port"), "5433")

    def test_connection_failure_multiple_ports_warns(self):
        self.script_happy_path()
        self.sockets.mkdir(parents=True)
        (self.sockets / ".s.PGSQL.5433").touch()
        (self.sockets / ".s.PGSQL.5434").touch()
        self.runner.expect("psql", returncode=2)
        self.runner.expect("psql", "--no-psqlrc", "-p", "5433", stdout="1\n")
        self.runner.expect("psql", "--no-psqlrc", "-p", "5434", stdout="1\n")

        result = self.invoke("init")

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("ports 5433, 5434", result.output)
        conf = OdooConf.load(self.home / ".config" / "odoo" / "odoo.conf")
        self.assertEqual(conf.get("db_port"), "False")

    def test_connection_failure_with_explicit_target_does_not_probe(self):
        conf_path = self.home / ".config" / "odoo" / "odoo.conf"
        conf_path.parent.mkdir(parents=True)
        conf_path.write_text("[options]\ndb_host = db.example.com\n")
        self.script_happy_path()
        self.sockets.mkdir(parents=True)
        (self.sockets / ".s.PGSQL.5433").touch()
        self.runner.expect("psql", returncode=2)

        result = self.invoke("init")

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("could not connect to PostgreSQL", result.output)
        probes = [c for c in self.runner.calls if c[0] == "psql" and "5433" in c]
        self.assertEqual(probes, [])
