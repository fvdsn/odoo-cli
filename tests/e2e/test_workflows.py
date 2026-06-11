"""Gated real-Odoo end-to-end flows (usecase.md).

These drive the real `odoo` entry point as a subprocess against a temporary
workspace — no CliRunner, no direct service calls. Opt-in and slow; meant for
manual runs and nightly CI, not the default contributor loop.

    ODOO_CLI_E2E=1 ODOO_CLI_E2E_ODOO_REPO=~/src/odoo \
        python -m unittest discover tests/e2e -v

Environment:

- ODOO_CLI_E2E=1            enables the suite
- ODOO_CLI_E2E_ODOO_REPO    path to a local odoo clone (avoids the network;
                            required — without it the suite is skipped)
- ODOO_CLI_E2E_VERSION      Odoo version branch (default: highest N.0 branch
                            of the source repo)
- ODOO_CLI_E2E_DB_PREFIX    prefix for the unique test databases
                            (default: odoocli-e2e)

Prerequisites: git, a reachable PostgreSQL (peer auth or db_* env), and
either uv or a python matching the target Odoo version.
"""

from __future__ import annotations

import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path

ENABLED = os.environ.get("ODOO_CLI_E2E") == "1"
ODOO_REPO = os.environ.get("ODOO_CLI_E2E_ODOO_REPO")
DB_PREFIX = os.environ.get("ODOO_CLI_E2E_DB_PREFIX", "odoocli-e2e")
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _git(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


@unittest.skipUnless(ENABLED, "set ODOO_CLI_E2E=1 to run the e2e suite")
@unittest.skipUnless(
    ODOO_REPO, "set ODOO_CLI_E2E_ODOO_REPO to a local odoo clone"
)
class TestV1Workflows(unittest.TestCase):
    """One workspace shared by all flows; methods are independent except for
    the class-level `odoo init` done once in setUpClass."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="odoo-cli-e2e-")
        base = Path(cls._tmp.name).resolve()
        cls.workspace = base / "workspace"
        cls.config_home = base / "config"
        cls.databases: set[str] = set()

        repos = cls.workspace / ".repositories"
        repos.mkdir(parents=True)
        # local bare clone of the cached odoo repo: no network
        _git("clone", "--bare", str(Path(ODOO_REPO).expanduser()),
             str(repos / "odoo.git"))
        cls.version = os.environ.get(
            "ODOO_CLI_E2E_VERSION"
        ) or cls._latest_stable(repos / "odoo.git")
        # a stub documentation repo with a matching branch keeps init
        # network-free; its content is irrelevant to these flows
        cls._make_stub_repo(base / "documentation-src", cls.version)
        _git("clone", "--bare", str(base / "documentation-src"),
             str(repos / "documentation.git"))

        code, out = cls._run_cls("init", cls.version, timeout=3600)
        assert code == 0, f"odoo init failed:\n{out}"

    @classmethod
    def tearDownClass(cls):
        for db in cls.databases:
            subprocess.run(["dropdb", db], capture_output=True)
        cls._tmp.cleanup()

    # -- harness -------------------------------------------------------------

    @classmethod
    def _env(cls) -> dict[str, str]:
        env = dict(os.environ)
        env["ODOO_DIR"] = str(cls.workspace)
        env["XDG_CONFIG_HOME"] = str(cls.config_home)
        env["PYTHONPATH"] = str(PROJECT_ROOT)  # python -m odoo_cli from any cwd
        env.pop("ODOO_RC", None)
        return env

    @classmethod
    def _run_cls(
        cls, *args: str, cwd: Path | None = None, timeout: int = 600
    ) -> tuple[int, str]:
        env = cls._env()
        if cwd is not None:
            # a shell would set the logical $PWD; subprocess does not, and
            # linked-worktree resolution depends on it
            env["PWD"] = str(cwd)
        proc = subprocess.run(
            [sys.executable, "-m", "odoo_cli", *args],
            cwd=cwd or PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout + proc.stderr

    def run_cli(self, *args, cwd=None, timeout=600) -> tuple[int, str]:
        return self._run_cls(*args, cwd=cwd, timeout=timeout)

    def unique_db(self) -> str:
        db = f"{DB_PREFIX}-{uuid.uuid4().hex[:6]}"
        self.databases.add(db)
        self.databases.add(f"{db}-test")
        return db

    @staticmethod
    def _latest_stable(repo: Path) -> str:
        branches = _git(
            "-C", str(repo), "for-each-ref", "refs/heads",
            "--format=%(refname:short)",
        ).splitlines()
        stable = [b for b in branches if re.fullmatch(r"\d+\.0", b)]
        assert stable, f"no N.0 branch in {repo}; set ODOO_CLI_E2E_VERSION"
        return max(stable, key=lambda b: int(b.split(".")[0]))

    @staticmethod
    def _make_stub_repo(path: Path, branch: str, addon: str | None = None):
        path.mkdir(parents=True)
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "e2e", "GIT_AUTHOR_EMAIL": "e2e@test",
            "GIT_COMMITTER_NAME": "e2e", "GIT_COMMITTER_EMAIL": "e2e@test",
        }

        def g(*args):
            subprocess.run(
                ["git", *args], cwd=path, check=True, capture_output=True,
                env=env,
            )

        if addon:
            module = path / addon
            module.mkdir()
            (module / "__manifest__.py").write_text(
                f"{{'name': '{addon}', 'version': '1.0', 'depends': ['base']}}\n"
            )
            (module / "__init__.py").write_text("")
        else:
            (path / "README").write_text("stub\n")
        g("init", "-q", "-b", branch)
        g("add", "-A")
        g("commit", "-qm", "initial")

    def wait_for_port(self, port: int, timeout: float = 300.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=2):
                    return
            except OSError:
                time.sleep(1)
        self.fail(f"port {port} never started listening")

    # -- flows ----------------------------------------------------------------

    def test_01_where_resolves_context(self):
        import json

        code, out = self.run_cli("where", "--json", cwd=self.workspace / self.version)
        self.assertEqual(code, 0, out)
        data = json.loads(out)
        self.assertEqual(data["worktree"], self.version)
        self.assertEqual(data["version"], self.version)
        self.assertEqual(data["database"], self.version)
        self.assertTrue(any("odoo-bin" in part for part in data["command"]))

    def test_02_install_reset_update_cycle(self):
        db = self.unique_db()
        # install works right after init (db created on demand)
        code, out = self.run_cli(
            "module", "install", "contacts", "-w", self.version, "-d", db
        )
        self.assertEqual(code, 0, out)
        # reset reinstalls the set read from the database
        code, out = self.run_cli("db", "reset", "-w", self.version, "-d", db)
        self.assertEqual(code, 0, out)
        self.assertIn("contacts", out)
        # the module survived the reset (db is the source of truth)
        code, out = self.run_cli(
            "shell", "-c",
            "print(env['ir.module.module'].search_count("
            "[('name','=','contacts'),('state','=','installed')]))",
            "-w", self.version, "-d", db,
        )
        self.assertEqual(code, 0, out)
        self.assertIn("1", out)
        # update the module
        code, out = self.run_cli(
            "update", "contacts", "-w", self.version, "-d", db
        )
        self.assertEqual(code, 0, out)

    def test_03_start_serves_http_and_keeps_ports_after_sigint(self):
        import json

        db = self.unique_db()
        proc = subprocess.Popen(
            [sys.executable, "-m", "odoo_cli", "start",
             "-w", self.version, "-d", db],
            cwd=PROJECT_ROOT,
            env=self._env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        try:
            ports_file = self.workspace / ".run" / self.version / db / "ports"
            deadline = time.monotonic() + 300
            while not ports_file.is_file() and time.monotonic() < deadline:
                if proc.poll() is not None:
                    self.fail(
                        f"odoo start exited early ({proc.returncode}):\n"
                        + proc.stdout.read()
                    )
                time.sleep(1)
            self.assertTrue(ports_file.is_file(), "ports file never appeared")
            http_port = int(
                dict(
                    line.split("=")
                    for line in ports_file.read_text().splitlines()
                )["http"]
            )
            self.wait_for_port(http_port)
            response = self._http_get(http_port, "/web/login")
            self.assertIn("HTTP/", response)

            # where (from another "terminal") sees the reserved ports
            code, out = self.run_cli(
                "where", "--json", "-w", self.version, "-d", db
            )
            data = json.loads(out)
            self.assertEqual(data["ports"]["http"], http_port)
            self.assertTrue(data["ports"]["reserved"])
        finally:
            os.killpg(os.getpgid(proc.pid), signal.SIGINT)  # as Ctrl-C would
            proc.wait(timeout=60)
        # the reservation survives the stop: stable across restarts
        self.assertTrue(ports_file.is_file())

    def test_04_linked_worktree_resolution_and_addons(self):
        import json

        base = Path(self._tmp.name) / "addon-src"
        self._make_stub_repo(base, self.version, addon="e2e_dummy_addon")

        code, out = self.run_cli(
            "repo", "add", "e2e-addons", str(base)
        )
        self.assertEqual(code, 0, out)
        code, out = self.run_cli(
            "worktree", "create", "customer-a", self.version,
            "--linked-from", self.version, "--addon", "e2e-addons",
        )
        self.assertEqual(code, 0, out)

        linked = self.workspace / "customer-a"
        self.assertTrue((linked / "odoo").is_symlink())
        self.assertTrue((linked / "e2e-addons" / "e2e_dummy_addon").is_dir())

        # target resolution from inside the linked worktree's symlinked odoo
        inside = linked / "odoo" / "addons"
        code, out = self.run_cli("where", "--json", cwd=inside)
        self.assertEqual(code, 0, out)
        data = json.loads(out)
        self.assertEqual(data["worktree"], "customer-a")
        self.assertEqual(data["linked_from"], self.version)
        self.assertEqual(data["database"], "customer-a")
        self.assertIn(str(linked / "e2e-addons"), data["addons_path"])

    @staticmethod
    def _http_get(port: int, path: str) -> str:
        with socket.create_connection(("127.0.0.1", port), timeout=10) as sock:
            sock.sendall(
                f"GET {path} HTTP/1.0\r\nHost: localhost\r\n\r\n".encode()
            )
            chunks = []
            sock.settimeout(10)
            try:
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    chunks.append(chunk)
            except TimeoutError:
                pass
            return b"".join(chunks).decode("utf-8", errors="replace")
