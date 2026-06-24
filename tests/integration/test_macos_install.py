"""Opt-in tart VM test for the install.sh fallback installer on macOS.

Docker can't host macOS, so the Homebrew branch of install.sh (`setup_macos`)
and the brew-based PostgreSQL install are exercised here instead: in a throwaway
macOS VM cloned from a cirruslabs base image and driven through `tart`
(Apple's Virtualization.framework — the right tool on Apple Silicon, where QEMU
can't boot macOS).

The cirruslabs `*-base` images are vanilla: Xcode Command Line Tools (so the
3.9 system python and git), but no Homebrew and no Python 3.10+. That is exactly
a fresh Mac, where install.sh's macOS path needs Homebrew. So the test first
provisions Homebrew (install.sh's documented prerequisite — "install it from
https://brew.sh"), then pipes install.sh through bash exactly as
`curl ... | bash` would. Success means the guest used brew to install
Python 3.10+ and git, unpacked the CLI, and completed `odoo init` including the
Homebrew PostgreSQL auto-install and a macOS-native Odoo venv.

This covers what Docker cannot: the brew install paths, brew-managed PostgreSQL,
and building Odoo's Python requirements on macOS/arm64.

Prerequisites:

- Apple Silicon host, macOS 13+ (tart needs Virtualization.framework)
- `tart` on PATH (or ODOO_CLI_TART_BIN), see https://tart.run
- a base image cloned locally, e.g.:
      tart clone ghcr.io/cirruslabs/macos-sequoia-base:latest sequoia-base
  (~25 GB compressed; pass its name via ODOO_CLI_TART_BASE)

Run with:

    ODOO_CLI_TART_E2E=1 ODOO_CLI_TART_BASE=sequoia-base \\
        python3 -m unittest tests.integration.test_macos_install

The cirruslabs base images ship with a standard admin/admin account over SSH.
OpenSSH reads passwords from the controlling terminal, not stdin, so we feed the
password through an SSH_ASKPASS helper (SSH_ASKPASS_REQUIRE=force) — no sshpass
or pexpect dependency, matching the project's stdlib-only stance.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

TART_E2E = os.environ.get("ODOO_CLI_TART_E2E") == "1"
BASE_IMAGE = os.environ.get("ODOO_CLI_TART_BASE", "sequoia-base")

SSH_USER = os.environ.get("ODOO_CLI_TART_SSH_USER", "admin")
SSH_PASS = os.environ.get("ODOO_CLI_TART_SSH_PASS", "admin")

#: virtio-fs share name -> auto-mounts at "/Volumes/My Shared Files/<name>" in
#: the macOS guest. install.sh only reads from it, so the share is read-only.
SHARE_NAME = "repo"
GUEST_SOURCE = f"/Volumes/My Shared Files/{SHARE_NAME}"

#: Apple Silicon Homebrew prefix; prepended to PATH so install.sh finds brew.
BREW_BIN = "/opt/homebrew/bin"
BREW_INSTALL_URL = (
    "https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh"
)


def _find_tart() -> str | None:
    candidate = os.environ.get("ODOO_CLI_TART_BIN") or shutil.which("tart")
    if candidate:
        return candidate
    fallback = Path.home() / ".local" / "bin" / "tart"
    return str(fallback) if fallback.exists() else None


@unittest.skipUnless(TART_E2E, "set ODOO_CLI_TART_E2E=1 to run tart VM e2e tests")
class TestMacosInstallScript(unittest.TestCase):
    def setUp(self):
        self.tart = _find_tart()
        if not self.tart:
            self.skipTest("tart not found (set ODOO_CLI_TART_BIN or install tart)")
        if BASE_IMAGE not in self._tart("list").stdout:
            self.skipTest(
                f"base image {BASE_IMAGE!r} not cloned; run "
                f"`tart clone ghcr.io/cirruslabs/macos-sequoia-base:latest {BASE_IMAGE}`"
            )
        self.vm = f"odoo-cli-e2e-{os.getpid()}"
        self._runner = None
        self._askpass = self._write_askpass()
        self.addCleanup(self._teardown)
        self._tart("clone", BASE_IMAGE, self.vm)

    # -- tart / ssh plumbing ----------------------------------------------

    def _tart(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(
            [self.tart, *args], text=True, capture_output=True, check=check
        )

    def _write_askpass(self) -> str:
        """A helper script SSH execs to obtain the password (it reads it from
        the environment we hand to ssh, so the secret never hits argv)."""
        fd, path = tempfile.mkstemp(prefix="tart-askpass-", suffix=".sh")
        with os.fdopen(fd, "w") as fh:
            fh.write('#!/bin/sh\nprintf "%s\\n" "$TART_SSH_PASS"\n')
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP)
        self.addCleanup(os.unlink, path)
        return path

    def _teardown(self) -> None:
        if self._runner and self._runner.poll() is None:
            self._tart("stop", self.vm, check=False)
            try:
                self._runner.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self._runner.kill()
        self._tart("delete", self.vm, check=False)

    def _boot(self) -> str:
        """Start the VM headless with the repo shared in, and return its IP
        once SSH answers."""
        self._runner = subprocess.Popen(
            [
                self.tart, "run", self.vm,
                "--no-graphics",
                f"--dir={SHARE_NAME}:{REPO_ROOT}:ro",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        ip = self._tart("ip", self.vm, "--wait", "120").stdout.strip()
        self.assertTrue(ip, "tart did not report a VM IP")
        self._wait_for_ssh(ip)
        return ip

    def _wait_for_ssh(self, ip: str, timeout: int = 240) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            rc, _ = self._ssh(ip, "true", timeout=20, check=False)
            if rc == 0:
                return
            time.sleep(5)
        self.fail(f"SSH to {self.vm} ({ip}) never became ready")

    def _ssh(
        self, ip: str, command: str, *, timeout: int = 3600, check: bool = True
    ) -> tuple[int, str]:
        """Run `command` in the guest over SSH, feeding the password through an
        askpass helper. Returns (exit status, combined output)."""
        env = dict(os.environ)
        env["SSH_ASKPASS"] = self._askpass
        env["SSH_ASKPASS_REQUIRE"] = "force"  # OpenSSH 8.4+: use askpass, no tty
        env["TART_SSH_PASS"] = SSH_PASS
        env.setdefault("DISPLAY", ":0")  # harmless; satisfies older ssh
        argv = [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ConnectTimeout=15",
            "-o", "LogLevel=ERROR",
            "-o", "NumberOfPasswordPrompts=1",
            f"{SSH_USER}@{ip}",
            command,
        ]
        try:
            proc = subprocess.run(
                argv,
                env=env,
                stdin=subprocess.DEVNULL,
                text=True,
                capture_output=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            output = (exc.output or "") + (exc.stderr or "")
            if check:
                self.fail(f"SSH command timed out after {timeout}s:\n{output}")
            return 124, output
        output = proc.stdout + proc.stderr
        if check and proc.returncode != 0:
            self.fail(f"SSH command failed ({proc.returncode}):\n{output}")
        return proc.returncode, output

    # -- the test ----------------------------------------------------------

    def _provision_homebrew(self, ip: str) -> None:
        """A developer Mac has Homebrew; the vanilla base image does not, so
        install it first (install.sh's documented macOS prerequisite)."""
        self._ssh(
            ip,
            "command -v brew >/dev/null 2>&1 || "
            f'NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL {BREW_INSTALL_URL})"',
            timeout=2400,
        )

    def test_install_script_bootstraps_a_workspace(self):
        ip = self._boot()
        self._provision_homebrew(ip)
        # deliver the script through a pipe, exactly as `curl ... | bash` does
        remote = (
            f'export PATH="{BREW_BIN}:$PATH"; '
            f"export ODOO_CLI_INSTALL_SOURCE='{GUEST_SOURCE}'; "
            'cat "$ODOO_CLI_INSTALL_SOURCE/install.sh" | bash'
        )
        rc, output = self._ssh(ip, remote, timeout=5400, check=False)
        self.assertEqual(rc, 0, output)
        self.assertIn("Installed the odoo command at", output)
        self.assertIn("Workspace ready", output)
