"""The only owner of odoo-bin CLI details.

Every odoo-bin invocation is built here as an OdooBinCommand. Rules
(docs/requirements.md → "Configuration via odoo.conf"):

- always pass `-c <shared odoo.conf>` explicitly, never rely on rcfile
  resolution (~/.odoorc, ODOO_RC)
- do NOT duplicate odoo.conf values into argv; only add the per-instance args
  that override the conf: --addons-path, -d, and allocated ports
- v1 passes no --data-dir (odoo-bin's default, shared data location)
- the postgres password is read from odoo.conf by odoo-bin itself, so argv
  never carries secrets and redacted_argv == argv

Version-dependent behavior lives in the capability table, which is also the
future delegation mechanism when odoo-bin adopts these conventions itself
(docs/requirements_v3.md → "Convention migration into odoo-bin").
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from odoo_cli.core import paths, release
from odoo_cli.core.addons import resolve_addons_paths
from odoo_cli.core.errors import UnsupportedOdooVersion
from odoo_cli.core.models import OdooBinCommand, Ports, Target

MIN_SUPPORTED_MAJOR = 17


@dataclass(frozen=True)
class Capabilities:
    """Per-version odoo-bin behavior. One entry per convention that either
    changed across supported versions or migrates into odoo-bin later."""

    #: odoo-bin has a native `module install` subcommand; older versions are
    #: polyfilled with `-i <modules> --stop-after-init`.
    native_module_install: bool


def capabilities_for(version: str) -> Capabilities:
    """Capabilities for a detected (normalized) version string.

    `17.0`..`19.0` are the supported stable lines; `saas-X.Y` follows its
    major; anything 20+ is the master line.
    """
    major = _major(version)
    if major < MIN_SUPPORTED_MAJOR:
        raise UnsupportedOdooVersion(
            f"Odoo {version} is not supported (oldest supported: "
            f"{MIN_SUPPORTED_MAJOR}.0)",
        )
    return Capabilities(native_module_install=major >= 20)


def _major(version: str) -> int:
    match = re.search(r"(\d+)", version)
    if not match:
        raise UnsupportedOdooVersion(f"unrecognized Odoo version '{version}'")
    return int(match.group(1))


class OdooBinService:
    def __init__(self, env: Mapping[str, str] | None = None):
        self.env: Mapping[str, str] = os.environ if env is None else env

    # -- builders ----------------------------------------------------------

    def server_start(
        self, target: Target, *, python: Path, ports: Ports, prod: bool = False
    ) -> OdooBinCommand:
        argv = self._base_argv(target)
        argv += ["--http-port", str(ports.http), "--gevent-port", str(ports.gevent)]
        if prod:
            argv += ["--dev", "none"]
        return self._command(target, python, argv, purpose="server start")

    def db_init(self, target: Target, *, python: Path) -> OdooBinCommand:
        """Initialize the target database empty (base only, no modules)."""
        argv = self._base_argv(target) + ["--stop-after-init", "--no-http"]
        return self._command(target, python, argv, purpose="db init")

    def module_install(
        self, target: Target, modules: list[str], *, python: Path
    ) -> OdooBinCommand:
        caps = self._capabilities(target)
        if caps.native_module_install:
            argv = self._base_argv(target, head=["module", "install", *modules])
        else:
            argv = self._base_argv(target) + [
                "-i", ",".join(modules), "--stop-after-init", "--no-http",
            ]
        return self._command(target, python, argv, purpose="module install")

    def module_update(
        self, target: Target, modules: list[str] | None, *, python: Path
    ) -> OdooBinCommand:
        names = ",".join(modules) if modules else "all"
        argv = self._base_argv(target) + [
            "-u", names, "--stop-after-init", "--no-http",
        ]
        return self._command(target, python, argv, purpose="module update")

    def tests(
        self,
        target: Target,
        modules: list[str],
        tags: list[str] | None = None,
        *,
        python: Path,
    ) -> OdooBinCommand:
        """Run tests against the conventional test database. No --no-http:
        HttpCase tests spawn their own server."""
        argv = self._base_argv(target, database=target.test_database)
        argv += ["-i", ",".join(modules), "--stop-after-init"]
        test_tags = [self._test_tag(t) for t in (tags or [])]
        if test_tags:
            argv += ["--test-tags", ",".join(test_tags)]
        else:
            argv += ["--test-enable"]
        return self._command(target, python, argv, purpose="tests")

    def shell(self, target: Target, *, python: Path) -> OdooBinCommand:
        argv = self._base_argv(target, head=["shell"]) + ["--no-http"]
        return self._command(target, python, argv, purpose="shell")

    # -- helpers -----------------------------------------------------------

    def conf_path(self) -> Path:
        return paths.odoo_conf_path(self.env)

    def _capabilities(self, target: Target) -> Capabilities:
        version = release.normalize_version(
            release.read_release(target.worktree.path).version
        )
        return capabilities_for(version)

    def _base_argv(
        self,
        target: Target,
        *,
        head: list[str] | None = None,
        database: str | None = None,
    ) -> list[str]:
        self._capabilities(target)  # version gate for every invocation
        addons = ",".join(str(p) for p in resolve_addons_paths(target.worktree))
        return [
            *(head or []),
            "-c", str(self.conf_path()),
            "-d", database or target.database,
            "--addons-path", addons,
        ]

    def _command(
        self, target: Target, python: Path, argv: list[str], *, purpose: str
    ) -> OdooBinCommand:
        odoo_bin = target.worktree.odoo_path / "odoo-bin"
        full_argv = [str(python), str(odoo_bin), *argv]
        return OdooBinCommand(
            executable=python,
            argv=full_argv,
            cwd=target.worktree.odoo_path,
            env={},
            redacted_argv=list(full_argv),  # argv never carries secrets
            purpose=purpose,
        )

    @staticmethod
    def _test_tag(tag: str) -> str:
        """`-t test_foo` resolves to odoo's test-tags format automatically."""
        if tag.startswith("test_"):
            return f".{tag}"
        return tag
