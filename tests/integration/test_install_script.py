"""Opt-in Docker test for the `curl https://www.odoo.com/install.sh | bash`
fallback installer.

Runs install.sh from a pipe (as curl would deliver it) in a bare Ubuntu 24.04
container: the script must apt-install Python/git/build deps, unpack the CLI
from the mounted checkout, and complete `odoo init` (including the PostgreSQL
auto-install). 24.04 has git >= 2.40, so init uses blobless clones; older
images (jammy: git 2.34) would full-clone for half an hour. The Python 3.10
floor is guarded separately by test_python_floor.

A second case runs the same installer under WSL-like conditions. WSL2 is a real
Linux kernel, so for a bash installer it is almost identical to plain Ubuntu;
the differences that actually bite are reproducible in Docker:

- no systemd as PID 1 (the WSL default), so PostgreSQL must start through
  `service`, not `systemctl` — which a default container already enforces;
- the WSL marker env vars (`WSL_DISTRO_NAME`, `WSL_INTEROP`) are present;
- Windows directories pollute `PATH` via interop.

Genuine Windows<->WSL interop (the Windows-supplied kernel, host networking,
drvfs mounts) needs a real Windows host and is covered separately by the
GitHub Actions Windows+WSL workflow, not here.

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

#: A PATH carrying the Windows interop directories WSL appends. The standard
#: Linux directories stay first, so tooling still resolves; the trailing
#: `/mnt/c/...` entries (absent inside the container) reproduce the pollution
#: that can trip up naive `command -v` lookups.
WSL_PATH = (
    "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:"
    "/mnt/c/Windows/system32:/mnt/c/Windows:/mnt/c/Windows/System32/WindowsPowerShell/v1.0"
)

#: install.sh only invokes `odoo` by absolute path and merely *warns* when
#: ~/.local/bin is off PATH; it never edits the shell profile. So the real
#: question is whether a normal user, after install, gets `odoo` on PATH with NO
#: manual step. We answer it faithfully: create an unprivileged sudo user
#: (PostgresService prefixes `sudo` when non-root, so `odoo init` still works),
#: install via curl|bash as that user, then — in a brand-new LOGIN shell (a fresh
#: terminal / re-login), with no PATH munging — see whether a bare `odoo`
#: resolves. The outcome is printed, not forced, so the run reports the truth.
INSTALL_AS_USER = (
    "set -e; "
    "apt-get update >/dev/null 2>&1 && apt-get install -y sudo >/dev/null 2>&1; "
    "useradd -m -s /bin/bash dev; "
    "echo 'dev ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/dev; "
    # install exactly as `curl ... | bash`, as the unprivileged user
    "su - dev -c 'ODOO_CLI_INSTALL_SOURCE=/src bash -c \"cat /src/install.sh | bash\"'; "
    # a fresh login shell, NO manual export — does bare `odoo` resolve?
    "echo '=== bare odoo check ==='; "
    "su - dev -c 'if command -v odoo >/dev/null 2>&1; then "
    'echo "BARE_ODOO: WORKS -> $(odoo --version)"; else echo BARE_ODOO: NOT-ON-PATH; fi\''
)


@unittest.skipUnless(
    DOCKER_E2E,
    "set ODOO_CLI_DOCKER_E2E=1 to run Docker e2e tests",
)
class TestInstallScript(unittest.TestCase):
    def _run_install(
        self, *docker_args: str, script: str
    ) -> subprocess.CompletedProcess:
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
            *docker_args,
            IMAGE,
            "/bin/bash",
            "-c",
            script,
        ]
        return subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # interleaved: assertions see everything
            check=False,
            timeout=3600,
        )

    def test_install_script_bootstraps_a_workspace(self):
        proc = self._run_install(script=INSTALL_AS_USER)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("Installed the odoo command at", proc.stdout)
        self.assertIn("Workspace ready", proc.stdout)
        # init must have auto-installed PostgreSQL (via sudo, as a normal user)
        self.assertIn("installing with apt-get", proc.stdout)
        self.assertIn("=== bare odoo check ===", proc.stdout)
        bare = next(
            (ln for ln in proc.stdout.splitlines() if "BARE_ODOO" in ln),
            "BARE_ODOO: ?",
        )
        print(f"\n[linux install e2e] {bare}\n")
        # install.sh must make `odoo` resolve for a normal user with no manual
        # step — a fresh login shell finds it on PATH
        self.assertIn("BARE_ODOO: WORKS", proc.stdout)

    def test_install_script_under_wsl_conditions(self):
        """install.sh in a WSL2-flavoured Ubuntu: WSL env markers present,
        Windows directories on PATH, and no systemd (so PostgreSQL has to come
        up via `service`). The full install -> init -> Postgres flow must still
        succeed."""
        # this case is about install/init robustness under PATH pollution, so it
        # runs the plain installer (as root); the bare-`odoo` PATH question is
        # covered by test_install_script_bootstraps_a_workspace
        proc = self._run_install(
            "-e",
            "WSL_DISTRO_NAME=Ubuntu-24.04",
            "-e",
            "WSL_INTEROP=/run/WSL/8_interop",
            "-e",
            f"PATH={WSL_PATH}",
            script="cat /src/install.sh | bash",
        )
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("Installed the odoo command at", proc.stdout)
        self.assertIn("Workspace ready", proc.stdout)
        # PostgreSQL had to install and start without systemd, the WSL default
        self.assertIn("installing with apt-get", proc.stdout)
