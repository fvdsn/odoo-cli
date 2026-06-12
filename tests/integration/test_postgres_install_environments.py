"""Opt-in Docker tests for the first-run PostgreSQL/Odoo flow.

These tests intentionally do not run in the normal suite. They install system
packages in disposable Docker containers, run `odoo init`, and verify that
`odoo start` serves HTTP.

Run Docker coverage:

    ODOO_CLI_DOCKER_E2E=1 python3 -m unittest \
        tests.integration.test_postgres_install_environments

"""

from __future__ import annotations

import os
import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

DOCKER_E2E = os.environ.get("ODOO_CLI_DOCKER_E2E") == "1"
VERSION = os.environ.get("ODOO_CLI_DOCKER_E2E_VERSION", "19.0")
IMAGE = os.environ.get("ODOO_CLI_DOCKER_E2E_IMAGE", "ubuntu:24.04")

FLOW = r"""
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

version = os.environ["ODOO_CLI_DOCKER_E2E_VERSION"]
expect_init = os.environ.get("ODOO_CLI_DOCKER_E2E_EXPECT_INIT")
expect_conf = os.environ.get("ODOO_CLI_DOCKER_E2E_EXPECT_CONF")
workspace = Path("/workspace/odoo")
config_home = Path("/workspace/config")
project_root = Path("/src")


def run(argv, *, cwd=None, timeout=600, env=None):
    proc = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise SystemExit(
            f"command failed ({proc.returncode}): {' '.join(map(str, argv))}\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    return proc.stdout + proc.stderr


def cli_env():
    env = dict(os.environ)
    env["ODOO_DIR"] = str(workspace)
    env["XDG_CONFIG_HOME"] = str(config_home)
    env["PYTHONPATH"] = str(project_root)
    env.pop("ODOO_RC", None)
    return env


def cli(*args, timeout=1800):
    return run(
        [sys.executable, "-m", "odoo_cli", *args],
        cwd=project_root,
        env=cli_env(),
        timeout=timeout,
    )


def http_get(port, path="/web/login"):
    with socket.create_connection(("127.0.0.1", port), timeout=10) as sock:
        sock.sendall(f"GET {path} HTTP/1.0\r\nHost: localhost\r\n\r\n".encode())
        sock.settimeout(10)
        chunks = []
        try:
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
        except TimeoutError:
            pass
    return b"".join(chunks).decode("utf-8", errors="replace")


def wait_for_http(port_file, proc, timeout=900):
    deadline = time.monotonic() + timeout
    while not port_file.is_file() and time.monotonic() < deadline:
        if proc.poll() is not None:
            raise SystemExit(
                f"odoo start exited before writing ports ({proc.returncode})\n"
                + proc.stdout.read()
            )
        time.sleep(1)
    if not port_file.is_file():
        raise SystemExit("odoo start did not write a ports file")

    ports = dict(line.split("=") for line in port_file.read_text().splitlines())
    port = int(ports["http"])
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise SystemExit(
                f"odoo start exited before serving HTTP ({proc.returncode})\n"
                + proc.stdout.read()
            )
        try:
            response = http_get(port)
            if "HTTP/" in response:
                return port, response
        except OSError:
            pass
        time.sleep(1)
    raise SystemExit(f"odoo did not serve HTTP on port {port}")


init_output = cli("init", version, timeout=2400)
if expect_init and expect_init not in init_output:
    raise SystemExit(f"odoo init output missing {expect_init!r}:\n{init_output}")
if "could not connect to PostgreSQL" in init_output:
    raise SystemExit(f"odoo init ended without a working connection:\n{init_output}")
if expect_conf:
    conf_text = (config_home / "odoo" / "odoo.conf").read_text()
    if expect_conf not in conf_text:
        raise SystemExit(f"odoo.conf missing {expect_conf!r}:\n{conf_text}")
if not (workspace / version / "odoo" / "odoo-bin").is_file():
    raise SystemExit("odoo init did not create the Odoo worktree")

db = "docker_e2e"
proc = subprocess.Popen(
    [sys.executable, "-m", "odoo_cli", "start", "-w", version, "-d", db],
    cwd=project_root,
    env=cli_env(),
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    start_new_session=True,
)
try:
    port, response = wait_for_http(
        workspace / ".run" / version / db / "ports",
        proc,
    )
    where = cli("where", "--json", "-w", version, "-d", db)
    data = json.loads(where)
    if data["ports"]["http"] != port or not data["ports"]["reserved"]:
        raise SystemExit(f"unexpected where output: {where}")
    print(f"odoo start served HTTP on {port}")
    print(response.splitlines()[0])
finally:
    if proc.poll() is None:
        os.killpg(os.getpgid(proc.pid), signal.SIGINT)
        proc.wait(timeout=90)
"""


@unittest.skipUnless(
    DOCKER_E2E,
    "set ODOO_CLI_DOCKER_E2E=1 to run Docker e2e tests",
)
class TestDockerFirstRun(unittest.TestCase):
    def run_flow(self, *, setup: str = "", expect: dict[str, str]) -> None:
        """Run FLOW in a disposable container; `setup` is extra shell run
        after the base packages, `expect` feeds the EXPECT_* env vars."""
        if not shutil.which("docker"):
            self.skipTest("docker not found")

        env_args = ["-e", f"ODOO_CLI_DOCKER_E2E_VERSION={VERSION}"]
        for key, value in expect.items():
            env_args += ["-e", f"ODOO_CLI_DOCKER_E2E_EXPECT_{key}={value}"]
        command = [
            "docker",
            "run",
            "--rm",
            "-i",
            "-v",
            f"{REPO_ROOT}:/src:ro",
            *env_args,
            IMAGE,
            "/bin/sh",
            "-lc",
            (
                "export DEBIAN_FRONTEND=noninteractive && "
                "apt-get update && "
                "apt-get install -y git python3 python3-venv python3-dev "
                "build-essential libpq-dev libldap2-dev libsasl2-dev && "
                + setup
                + "PYTHONPATH=/src python3 -"
            ),
        ]
        proc = subprocess.run(
            command,
            input=FLOW,
            text=True,
            capture_output=True,
            check=False,
            timeout=3600,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("odoo start served HTTP", proc.stdout)

    def test_init_installs_postgres_and_start_serves_http(self):
        self.run_flow(
            expect={
                "INIT": "PostgreSQL is not installed; installing with apt-get",
            },
        )

    def test_init_adopts_preinstalled_postgres_on_custom_port(self):
        """The tester scenario: PostgreSQL already installed but listening on
        a non-standard port. init must detect the port, save db_port, and
        `odoo start` must work with it."""
        self.run_flow(
            setup=(
                "apt-get install -y postgresql && "
                "sed -i 's/^port = .*/port = 6543/' "
                "/etc/postgresql/*/main/postgresql.conf && "
                "service postgresql start && "
                "runuser -u postgres -- createuser -p 6543 --superuser root && "
            ),
            expect={
                "INIT": "PostgreSQL answers on port 6543",
                "CONF": "db_port = 6543",
            },
        )
