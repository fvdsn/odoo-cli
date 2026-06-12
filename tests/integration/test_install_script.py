"""Opt-in Docker test for the `curl https://www.odoo.com/install.sh | bash`
fallback installer.

Runs install.sh from a pipe (as curl would deliver it) in a bare Ubuntu 24.04
container: the script must apt-install Python/git/build deps, unpack the CLI
from the mounted checkout, and complete `odoo init` (including the PostgreSQL
auto-install). 24.04 has git >= 2.40, so init uses blobless clones; older
images (jammy: git 2.34) would full-clone for half an hour. The Python 3.10
floor is guarded separately by test_python_floor.

Run with:

    ODOO_CLI_DOCKER_E2E=1 python3 -m unittest tests.integration.test_install_script

"""

from __future__ import annotations

import os
import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

DOCKER_E2E = os.environ.get("ODOO_CLI_DOCKER_E2E") == "1"
IMAGE = os.environ.get("ODOO_CLI_DOCKER_E2E_INSTALL_IMAGE", "ubuntu:24.04")


@unittest.skipUnless(
    DOCKER_E2E,
    "set ODOO_CLI_DOCKER_E2E=1 to run Docker e2e tests",
)
class TestInstallScript(unittest.TestCase):
    def test_install_script_bootstraps_a_workspace(self):
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
            "ODOO_CLI_INSTALL_SOURCE=/src",
            IMAGE,
            "/bin/bash",
            "-c",
            # `cat | bash` reproduces how curl delivers the script: bash
            # reads it from a pipe, with no file on disk and stdin occupied
            "cat /src/install.sh | bash",
        ]
        proc = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # interleaved: assertions see everything
            check=False,
            timeout=3600,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("Installed the odoo command at", proc.stdout)
        self.assertIn("Workspace ready", proc.stdout)
        # init must have auto-installed PostgreSQL inside the container
        self.assertIn("installing with apt-get", proc.stdout)
