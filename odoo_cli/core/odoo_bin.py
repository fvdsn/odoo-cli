"""The only owner of odoo-bin CLI details.

Every odoo-bin invocation is built here as an OdooBinCommand. Rules
(specs/requirements.md → "Configuration via odoo.conf"):

- always pass `-c <shared odoo.conf>` explicitly, never rely on rcfile
  resolution (~/.odoorc, ODOO_RC)
- do NOT duplicate odoo.conf values into argv; only add the per-instance args
  that override the conf: --addons-path, -d, and allocated ports
- v1 passes no --data-dir (odoo-bin's default, shared data location)
- the postgres password is read from odoo.conf by odoo-bin itself, so argv
  never carries secrets and redacted_argv == argv

Version-dependent behavior lives in the capability table, which is also the
future delegation mechanism when odoo-bin adopts these conventions itself
(specs/requirements_v3.md → "Convention migration into odoo-bin").
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from odoo_cli.core import paths, release
from odoo_cli.core.addons import resolve_addons_paths
from odoo_cli.core.errors import ProcessFailed, UnsupportedOdooVersion
from odoo_cli.core.models import OdooBinCommand, Ports, Target
from odoo_cli.util.process import ProcessRunner

MIN_SUPPORTED_MAJOR = 17


def run_streamed(runner: ProcessRunner, command: OdooBinCommand) -> None:
    """Stream an odoo-bin command in the terminal, raising on failure.

    The shared execution path for install/update/init runs: output goes to
    the terminal as it happens (a module install can take minutes)."""
    code = runner.stream(command.argv, cwd=command.cwd, extra_env=command.env)
    if code != 0:
        raise ProcessFailed(
            f"{command.purpose} failed (odoo-bin exited {code})",
            argv=command.redacted_argv,
            returncode=code,
        )


@dataclass(frozen=True)
class Capabilities:
    """Per-version odoo-bin behavior. One entry per convention that either
    changed across supported versions or migrates into odoo-bin later."""

    #: odoo-bin has a native `module install` subcommand; older versions are
    #: polyfilled with `-i <modules> --stop-after-init`.
    native_module_install: bool

    #: odoo-bin has `db init` (create + initialize with odoo's own creation
    #: semantics: encoding, C collation, template0); older versions are
    #: polyfilled with `createdb` + `-i base --stop-after-init`.
    native_db_init: bool


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
    return Capabilities(
        native_module_install=major >= 20,
        native_db_init=major >= 19,
    )


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
        """Initialize the target database empty (base only, no modules).

        The explicit `-i base` matters: without an install/update request,
        odoo-bin exits 0 on an empty database without initializing it."""
        argv = self._base_argv(target) + [
            "-i", "base", "--stop-after-init", "--no-http",
        ]
        return self._command(target, python, argv, purpose="db init")

    def db_create_init(
        self, target: Target, *, python: Path, demo: bool
    ) -> OdooBinCommand:
        """Create and initialize the target database via odoo-bin's own
        `db init` (native_db_init capability): the creation semantics —
        encoding, C collation, template0, filestore — stay odoo's, not ours.

        No `_base_argv` here: the `db` command takes no `-d` (the database is
        positional) and no ports. Demo is passed explicitly because `db init`
        reads only its `--with-demo` flag, never odoo.conf's without_demo."""
        self._capabilities(target)  # version gate for every invocation
        addons = ",".join(str(p) for p in resolve_addons_paths(target.worktree))
        argv = [
            "db", "-c", str(self.conf_path()), "--addons-path", addons,
            "init", *(["--with-demo"] if demo else []), target.database,
        ]
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
        install: list[str],
        update: list[str] | None = None,
        tags: list[str] | None = None,
        *,
        python: Path,
    ) -> OdooBinCommand:
        """Run tests against the conventional test database. No --no-http:
        HttpCase tests spawn their own server.

        odoo-bin only runs tests for modules it installs or updates in this
        very process, so modules already installed in a reused test database
        must arrive in `update` — under -i they are silently skipped and
        their tests never run."""
        argv = self._base_argv(target, database=target.test_database)
        if install:
            argv += ["-i", ",".join(install)]
        if update:
            argv += ["-u", ",".join(update)]
        # tests never inherit odoo.conf's dev_mode: dev reload/xml modes
        # change caching and query shapes, failing e.g. assertQueries suites
        # wholesale (runbot semantics are dev-off). Crons are disabled the
        # way runbot does it: the HttpCase server would otherwise spawn cron
        # workers whose jobs (mail queue, autovacuum) mutate state mid-test.
        argv += [
            "--stop-after-init", "--dev", "none", "--max-cron-threads", "0",
        ]
        # the shared conf's log_level=warn would swallow test results and
        # the at_install/post_install phase markers; surface exactly those
        for handler in ("odoo.tests:INFO", "odoo.modules.loading:INFO",
                        "odoo.service.server:INFO"):
            argv += ["--log-handler", handler]
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

    def capabilities(self, target: Target) -> Capabilities:
        """The capability table for the target's detected version; services
        use it to pick between native odoo-bin subcommands and polyfills."""
        return self._capabilities(target)

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
            env=self._venv_path_env(python),
            redacted_argv=list(full_argv),  # argv never carries secrets
            purpose=purpose,
        )

    def _venv_path_env(self, python: Path) -> dict[str, str]:
        """PATH with the venv's bin first, as activating the venv would set
        it: odoo code looks up venv-installed executables by PATH (the
        pylint binary in test_lint, ...) and would otherwise miss them."""
        current = self.env.get("PATH", "")
        bin_dir = str(python.parent)
        return {"PATH": f"{bin_dir}{os.pathsep}{current}" if current else bin_dir}

    @staticmethod
    def _test_tag(tag: str) -> str:
        """`-t test_foo` resolves to odoo's test-tags format automatically."""
        if tag.startswith("test_"):
            return f".{tag}"
        return tag
