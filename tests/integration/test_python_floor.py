"""Opt-in Docker test guarding the Python 3.10 floor (requires-python).

Ubuntu 22.04 LTS (supported until April 2027) ships Python 3.10 and is the
oldest interpreter the CLI promises to run on. This runs the full unit/CLI
suite on jammy's real 3.10 — fast (no clones, no network beyond apt) compared
to the install-script e2e, which uses a newer image for blobless clones.

Run with:

    ODOO_CLI_DOCKER_E2E=1 python3 -m unittest tests.integration.test_python_floor

"""

from __future__ import annotations

import os
import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

DOCKER_E2E = os.environ.get("ODOO_CLI_DOCKER_E2E") == "1"
IMAGE = os.environ.get("ODOO_CLI_DOCKER_E2E_FLOOR_IMAGE", "ubuntu:22.04")


@unittest.skipUnless(
    DOCKER_E2E,
    "set ODOO_CLI_DOCKER_E2E=1 to run Docker e2e tests",
)
class TestPythonFloor(unittest.TestCase):
    def test_suite_passes_on_python_310(self):
        if not shutil.which("docker"):
            self.skipTest("docker not found")

        command = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{REPO_ROOT}:/src:ro",
            "-w",
            "/src",
            IMAGE,
            "/bin/sh",
            "-lc",
            (
                "export DEBIAN_FRONTEND=noninteractive && "
                "apt-get update -qq && "
                "apt-get install -y -qq python3 git >/dev/null && "
                "python3 --version && "
                "python3 -m unittest discover"
            ),
        ]
        proc = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=1200,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("Python 3.10", proc.stdout)
        self.assertIn("OK", proc.stdout)
