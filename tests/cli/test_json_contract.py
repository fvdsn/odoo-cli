"""The machine-readable surface an external frontend drives: --json output
on queries and mutations, and the JSON error envelope from `main`."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from odoo_cli.cli._click import click, testing
from odoo_cli.cli.context import CliContext, Services
from odoo_cli.cli.main import cli, main
from odoo_cli.core.errors import DatabaseNotFound
from odoo_cli.core.venvs import READY_MARKER
from tests.fixtures.process import FakeProcessRunner
from tests.fixtures.workspace import make_env, make_workspace, make_worktree

LIST_DBS_QUERY = (
    "SELECT datname, pg_database_size(datname), pg_get_userbyid(datdba) "
    "FROM pg_database WHERE NOT datistemplate AND datname <> 'postgres' "
    "ORDER BY datname"
)
BASE_VERSION_QUERY = "SELECT latest_version FROM ir_module_module WHERE name = 'base'"


class JsonContractTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name).resolve()
        self.env = make_env(self.home)
        self.root = make_workspace(self.home)
        make_worktree(self.root, "19.0", version="19.0")
        self.data_dir = self.home / "odoo-data"
        conf = self.home / ".config" / "odoo" / "odoo.conf"
        conf.parent.mkdir(parents=True)
        conf.write_text(f"[options]\ndata_dir = {self.data_dir}\n")
        self.runner = FakeProcessRunner()
        self.cli_runner = testing.CliRunner()
        venv = self.root / ".venvs" / "19.0"
        (venv / "bin").mkdir(parents=True)
        (venv / "bin" / "python").write_text("")
        (venv / READY_MARKER).touch()
        self.python = str(venv / "bin" / "python")

    def invoke(self, *args):
        services = Services(process=self.runner, env=self.env)
        return self.cli_runner.invoke(cli, list(args), obj=CliContext(services=services))

    def payload(self, result):
        self.assertEqual(result.exit_code, 0, result.output)
        # stdout must be exactly one JSON document; progress goes to stderr
        return json.loads(result.stdout)


class TestWhereJson(JsonContractTestCase):
    def test_run_contract_fields(self):
        data = self.payload(self.invoke("where", "--json"))
        odoo_dir = self.root / "19.0" / "odoo"
        self.assertEqual(data["python"], self.python)
        self.assertEqual(data["odoo_bin"], str(odoo_dir / "odoo-bin"))
        self.assertEqual(data["cwd"], str(odoo_dir))
        self.assertEqual(data["env"], {})
        self.assertEqual(data["command"][0], self.python)
        # unset conf keys surface as null, matching Odoo's "False is unset"
        self.assertEqual(
            data["postgres"], {"host": None, "port": None, "user": None}
        )


class TestWorktreeListJson(JsonContractTestCase):
    def test_lists_worktrees(self):
        data = self.payload(self.invoke("worktree", "list", "--json"))
        (entry,) = data["worktrees"]
        self.assertEqual(entry["name"], "19.0")
        self.assertEqual(entry["path"], str(self.root / "19.0"))
        self.assertEqual(entry["version"], "19.0")
        self.assertIsNone(entry["linked_from"])
        self.assertIn("valid", entry)
        self.assertEqual(entry["repos"], [])  # no real git checkouts in the fixture

    def test_reports_checkout_branches(self):
        odoo_dir = self.root / "19.0" / "odoo"
        (odoo_dir / ".git").mkdir()
        self.runner.expect(
            "git", "-C", str(odoo_dir), "symbolic-ref", stdout="19.0-fix\n"
        )
        data = self.payload(self.invoke("worktree", "list", "--json"))
        (entry,) = data["worktrees"]
        self.assertEqual(entry["repos"], [{"name": "odoo", "branch": "19.0-fix"}])


class TestDbListJson(JsonContractTestCase):
    def test_lists_databases_with_metadata(self):
        self.runner.expect(
            "psql", "--no-psqlrc", "-tAc", LIST_DBS_QUERY,
            stdout="alpha|123456|fred\nscratch|500|fred\n",
        )
        self.runner.expect("psql", "--no-psqlrc", "-tAc", BASE_VERSION_QUERY, stdout="")
        result = self.invoke("db", "list", "--json")
        data = self.payload(result)
        self.assertEqual(
            data["databases"],
            [
                {
                    "name": "alpha",
                    "size_bytes": 123456,
                    "owner": "fred",
                    "version": None,
                    "filestore": None,
                },
                {
                    "name": "scratch",
                    "size_bytes": 500,
                    "owner": "fred",
                    "version": None,
                    "filestore": None,
                },
            ],
        )

    def test_reports_version_and_filestore(self):
        store = self.data_dir / "filestore" / "alpha"
        store.mkdir(parents=True)
        self.runner.expect(
            "psql", "--no-psqlrc", "-tAc", LIST_DBS_QUERY, stdout="alpha|1|fred\n"
        )
        self.runner.expect(
            "psql", "--no-psqlrc", "-tAc", BASE_VERSION_QUERY, stdout="19.0.1.0.0\n"
        )
        data = self.payload(self.invoke("db", "list", "--json"))
        (entry,) = data["databases"]
        self.assertEqual(entry["version"], "19.0.1.0.0")
        self.assertEqual(entry["filestore"], str(store))


class TestDbCloneRename(JsonContractTestCase):
    def _expect_pair(self, source: str, target: str):
        self.runner.expect("psql", stdout="")  # catch-all: no rows
        self.runner.expect(
            "psql", "--no-psqlrc", "-tAc",
            f"SELECT 1 FROM pg_database WHERE datname = '{source}'",
            stdout="1\n",
        )

    def test_clone_copies_filestore(self):
        store = self.data_dir / "filestore" / "alpha"
        store.mkdir(parents=True)
        (store / "blob").write_text("x")
        self._expect_pair("alpha", "beta")
        self.runner.expect("createdb")
        data = self.payload(self.invoke("db", "clone", "alpha", "beta", "--json"))
        self.assertEqual(
            data, {"source": "alpha", "database": "beta", "filestore_copied": True}
        )
        self.assertIn(("createdb", "-T", "alpha", "beta"), self.runner.calls)
        self.assertEqual(
            (self.data_dir / "filestore" / "beta" / "blob").read_text(), "x"
        )
        self.assertTrue(store.is_dir())  # the source keeps its filestore

    def test_rename_moves_filestore(self):
        store = self.data_dir / "filestore" / "alpha"
        store.mkdir(parents=True)
        (store / "blob").write_text("x")
        self._expect_pair("alpha", "beta")
        data = self.payload(self.invoke("db", "rename", "alpha", "beta", "--json"))
        self.assertEqual(
            data, {"database": "beta", "renamed_from": "alpha", "filestore_moved": True}
        )
        self.assertFalse(store.exists())
        self.assertEqual(
            (self.data_dir / "filestore" / "beta" / "blob").read_text(), "x"
        )
        alter = [c for c in self.runner.calls if any("ALTER DATABASE" in a for a in c)]
        self.assertTrue(alter)

    def test_clone_missing_source_is_an_error(self):
        self.runner.expect("psql", stdout="")  # no database exists
        result = self.invoke("db", "clone", "nope", "copy", "--json")
        self.assertEqual(result.exit_code, 1)


class TestMutationJson(JsonContractTestCase):
    def test_module_install_json(self):
        self.runner.expect("psql", stdout="1\n")  # db exists and is initialized
        result = self.invoke("module", "install", "crm", "sale", "--json")
        data = self.payload(result)
        self.assertEqual(data, {"installed": ["crm", "sale"], "database": "19.0"})

    def test_module_install_preflight_installs_missing_dep(self):
        mod = self.root / "19.0" / "odoo" / "addons" / "mod_p"
        mod.mkdir(parents=True)
        (mod / "__manifest__.py").write_text(
            "{'name': 'P', 'external_dependencies': {'python': ['phonenumbers']}}"
        )
        self.runner.expect("psql", stdout="1\n")
        self.runner.expect(self.python, "-c", stdout="phonenumbers\n")
        self.runner.expect("uv", stdout="")  # whichever installer the box has
        self.runner.expect(self.python, "-m", "pip", stdout="")
        result = self.invoke("module", "install", "mod_p", "--json")
        data = self.payload(result)
        self.assertEqual(data["installed"], ["mod_p"])
        self.assertTrue(
            any("install" in c and "phonenumbers" in c for c in self.runner.calls)
        )

    def test_db_reset_json(self):
        self.runner.expect("psql", stdout="1\n")
        self.runner.expect(
            "psql", "--no-psqlrc", "-tAc",
            "SELECT name FROM ir_module_module WHERE state = 'installed'",
            stdout="base\ncrm\n",
        )
        self.runner.expect(
            "dropdb", stdout="",
            effect=lambda call: self.runner.expect(
                "psql", "--no-psqlrc", "-tAc",
                "SELECT 1 FROM pg_database WHERE datname = '19.0'",
                stdout="",
            ),
        )
        self.runner.expect("createdb", stdout="")
        result = self.invoke("db", "reset", "--json")
        data = self.payload(result)
        self.assertEqual(data, {"database": "19.0", "reinstalled": ["crm"]})


class TestJsonErrorEnvelope(unittest.TestCase):
    def test_error_envelope_on_stdout(self):
        @click.pass_obj
        def boom(ctx):
            ctx.output.json_mode = True
            raise DatabaseNotFound("database 'x' does not exist", hint="odoo db list")

        cli.add_command(click.command(name="boom-json")(boom))
        self.addCleanup(cli.commands.pop, "boom-json")
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["boom-json"])
        self.assertEqual(code, 1)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(
            payload["error"],
            {
                "code": "database_not_found",
                "message": "database 'x' does not exist",
                "hint": "odoo db list",
            },
        )
