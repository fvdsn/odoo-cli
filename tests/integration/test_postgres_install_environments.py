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
if "PostgreSQL is not installed; installing with apt-get" not in init_output:
    raise SystemExit("odoo init did not exercise PostgreSQL auto-install")
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
    def test_init_installs_postgres_and_start_serves_http(self):
        if not shutil.which("docker"):
            self.skipTest("docker not found")

        command = [
            "docker",
            "run",
            "--rm",
            "-i",
            "-v",
            f"{REPO_ROOT}:/src:ro",
            "-e",
            f"ODOO_CLI_DOCKER_E2E_VERSION={VERSION}",
            IMAGE,
            "/bin/sh",
            "-lc",
            (
                "export DEBIAN_FRONTEND=noninteractive && "
                "apt-get update && "
                "apt-get install -y git python3 python3-venv python3-dev "
                "build-essential libpq-dev libldap2-dev libsasl2-dev && "
                "PYTHONPATH=/src python3 -"
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
