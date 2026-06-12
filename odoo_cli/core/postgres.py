"""PostgreSQL access for the CLI's own needs (checks, createdb, SQL).

The connection comes from the `db_*` keys in odoo.conf. Odoo's convention for
"unset" is the string "False"; those keys are simply not exported. The
password travels via PGPASSWORD, never on a command line.
"""

from __future__ import annotations

import getpass
import os
import shlex
import shutil
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from odoo_cli.core.errors import PostgresError
from odoo_cli.core.odoo_conf import OdooConf, is_set
from odoo_cli.util.process import ProcessError, ProcessRunner

_ENV_KEYS = {
    "db_host": "PGHOST",
    "db_port": "PGPORT",
    "db_user": "PGUSER",
    "db_password": "PGPASSWORD",
}

#: Where a local server creates its `.s.PGSQL.<port>` socket file:
#: Debian/Ubuntu use /var/run/postgresql, Homebrew/macOS default to /tmp.
_SOCKET_DIRS = (Path("/var/run/postgresql"), Path("/tmp"))


@dataclass(frozen=True)
class PostgresInstallPlan:
    manager: str
    install_commands: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class PostgresInstallResult:
    manager: str
    warnings: tuple[str, ...] = ()


def quote_literal(value: str) -> str:
    """SQL string literal with quotes doubled. Names reaching this module are
    already validated (TargetResolver), this is the second line of defense."""
    return "'" + value.replace("'", "''") + "'"


class PostgresService:
    def __init__(
        self,
        runner: ProcessRunner,
        which: Callable[[str], str | None] = shutil.which,
        *,
        platform: str | None = None,
        geteuid: Callable[[], int | None] | None = None,
        current_user: Callable[[], str] | None = None,
        socket_dirs: tuple[Path, ...] | None = None,
        environ: Mapping[str, str] | None = None,
    ):
        self.runner = runner
        self.which = which
        self.platform = sys.platform if platform is None else platform
        self.socket_dirs = _SOCKET_DIRS if socket_dirs is None else socket_dirs
        self.environ = os.environ if environ is None else environ
        self.geteuid = (
            getattr(os, "geteuid", lambda: None)
            if geteuid is None
            else geteuid
        )
        self.current_user = getpass.getuser if current_user is None else current_user

    def env(self, conf: OdooConf) -> dict[str, str]:
        env = {}
        for key, var in _ENV_KEYS.items():
            value = conf.get(key)
            if is_set(value):
                env[var] = value
        return env

    def is_installed(self) -> bool:
        return self.which("psql") is not None

    def install_plan(self) -> PostgresInstallPlan:
        """Return the native package-manager commands for this platform."""
        if self.platform == "darwin":
            if not self.which("brew"):
                raise PostgresError(
                    "PostgreSQL is not installed and Homebrew was not found",
                    hint=(
                        "install Homebrew or PostgreSQL manually, then re-run "
                        "`odoo init`"
                    ),
                )
            return PostgresInstallPlan(
                manager="Homebrew",
                install_commands=(("brew", "install", "postgresql"),),
            )

        if self.platform.startswith("linux"):
            if not self.which("apt-get"):
                raise PostgresError(
                    "PostgreSQL is not installed and apt-get was not found",
                    hint=(
                        "install PostgreSQL with your system package manager, "
                        "then re-run `odoo init`"
                    ),
                )
            prefix = self._admin_prefix()
            apt = prefix + ("env", "DEBIAN_FRONTEND=noninteractive", "apt-get")
            return PostgresInstallPlan(
                manager="apt-get",
                install_commands=(
                    apt + ("update",),
                    apt + ("install", "-y", "postgresql"),
                ),
            )

        raise PostgresError(
            f"PostgreSQL is not installed on unsupported platform {self.platform!r}",
            hint="install PostgreSQL manually, then re-run `odoo init`",
        )

    def install(self) -> PostgresInstallResult:
        """Install PostgreSQL with the platform package manager.

        Package-manager output streams directly to the terminal because these
        commands can be long-running and may need sudo interaction.
        """
        plan = self.install_plan()
        for command in plan.install_commands:
            code = self.runner.stream(list(command))
            if code != 0:
                raise PostgresError(
                    "could not install PostgreSQL",
                    hint=f"failed command: {shlex.join(command)}",
                )

        warnings = []
        start_warning = self._start_after_install()
        if start_warning:
            warnings.append(start_warning)
        elif plan.manager == "apt-get":
            role_warning = self._ensure_current_user_role()
            if role_warning:
                warnings.append(role_warning)

        if not self.is_installed():
            raise PostgresError(
                "PostgreSQL installation finished but psql was not found",
                hint="make sure PostgreSQL's bin directory is on PATH, then re-run `odoo init`",
            )

        return PostgresInstallResult(manager=plan.manager, warnings=tuple(warnings))

    def _admin_prefix(self) -> tuple[str, ...]:
        if self.geteuid() == 0:
            return ()
        if self.which("sudo"):
            return ("sudo",)
        raise PostgresError(
            "PostgreSQL is not installed and administrator privileges are needed",
            hint="run `odoo init` as root or install sudo, then try again",
        )

    def _start_after_install(self) -> str | None:
        commands = self._start_commands()
        if not commands:
            return "could not find a service manager to start PostgreSQL automatically"
        failed = []
        for command in commands:
            code = self.runner.stream(list(command))
            if code == 0:
                return None
            failed.append(shlex.join(command))
        return (
            "could not start PostgreSQL automatically; try manually with: "
            + " or ".join(failed)
        )

    def _start_commands(self) -> tuple[tuple[str, ...], ...]:
        if self.platform == "darwin":
            if self.which("brew"):
                return (("brew", "services", "start", "postgresql"),)
            return ()
        if self.platform.startswith("linux"):
            prefix = self._admin_prefix()
            commands = []
            if self.which("systemctl"):
                commands.append(prefix + ("systemctl", "start", "postgresql"))
            if self.which("service"):
                commands.append(prefix + ("service", "postgresql", "start"))
            return tuple(commands)
        return ()

    def _ensure_current_user_role(self) -> str | None:
        """Debian/Ubuntu PostgreSQL creates a `postgres` role, not a role for
        the current OS user. The CLI defaults to local peer auth, so make that
        first-run path work after an automatic apt install."""
        user = self.current_user()
        prefix = self._postgres_admin_prefix()
        if prefix is None:
            return (
                "could not create a PostgreSQL role for the current OS user; "
                "create one manually or set db_user with `odoo config set`"
            )
        result = self.runner.run(
            [*prefix, "createuser", "--superuser", user],
            check=False,
        )
        if result.returncode == 0 or "already exists" in result.stderr:
            return None
        return (
            "could not create a PostgreSQL role for the current OS user; "
            f"try manually with: {shlex.join((*prefix, 'createuser', '--superuser', user))}"
        )

    def _postgres_admin_prefix(self) -> tuple[str, ...] | None:
        if self.geteuid() == 0:
            if self.which("runuser"):
                return ("runuser", "-u", "postgres", "--")
            return None
        if self.which("sudo"):
            return ("sudo", "-u", "postgres")
        return None

    def check_connection(self, conf: OdooConf) -> bool:
        # Debian's psql is a wrapper that finds the cluster's real port on
        # its own; pin the port libpq would use so the check reflects what
        # Odoo will do, not what the wrapper can figure out.
        env = self.env(conf)
        port = env.get("PGPORT") or self.environ.get("PGPORT") or "5432"
        result = self.runner.run(
            ["psql", "--no-psqlrc", "-p", port, "-tAc", "SELECT 1", "postgres"],
            extra_env=env,
            check=False,
        )
        return result.returncode == 0

    def detect_local_ports(self, conf: OdooConf) -> list[int]:
        """Ports of local servers that answer `SELECT 1`.

        A running server advertises its port as the suffix of its
        `.s.PGSQL.<port>` socket file; `pg_lsclusters` (Debian/Ubuntu)
        additionally covers clusters with a non-standard socket directory.
        """
        candidates: set[int] = set()
        for directory in self.socket_dirs:
            for socket in directory.glob(".s.PGSQL.*"):
                port = socket.name.rsplit(".", 1)[-1]
                if port.isdigit():
                    candidates.add(int(port))
        if self.which("pg_lsclusters"):
            result = self.runner.run(["pg_lsclusters", "--no-header"], check=False)
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    parts = line.split()  # Ver Cluster Port Status ...
                    if len(parts) >= 4 and parts[2].isdigit() and "online" in parts[3]:
                        candidates.add(int(parts[2]))
        return [port for port in sorted(candidates) if self._answers(conf, port)]

    def _answers(self, conf: OdooConf, port: int) -> bool:
        result = self.runner.run(
            ["psql", "--no-psqlrc", "-p", str(port), "-tAc", "SELECT 1", "postgres"],
            extra_env=self.env(conf),
            check=False,
        )
        return result.returncode == 0

    def db_exists(self, conf: OdooConf, name: str) -> bool:
        rows = self.sql(
            conf,
            "postgres",
            f"SELECT 1 FROM pg_database WHERE datname = {quote_literal(name)}",
        )
        return bool(rows)

    def create_db(self, conf: OdooConf, name: str) -> None:
        try:
            self.runner.run(["createdb", name], extra_env=self.env(conf))
        except ProcessError as exc:
            raise PostgresError(
                f"could not create database '{name}'",
                hint=exc.result.stderr.strip() or None,
            ) from exc

    def drop_db(self, conf: OdooConf, name: str) -> None:
        """Terminates open connections first, then drops."""
        self.sql(
            conf,
            "postgres",
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = {quote_literal(name)} "
            "AND pid <> pg_backend_pid()",
        )
        try:
            self.runner.run(["dropdb", name], extra_env=self.env(conf))
        except ProcessError as exc:
            raise PostgresError(
                f"could not drop database '{name}'",
                hint=exc.result.stderr.strip() or None,
            ) from exc

    def sql(self, conf: OdooConf, database: str, query: str) -> list[str]:
        """Run a query, one result row per line (tuples-only output)."""
        try:
            result = self.runner.run(
                ["psql", "--no-psqlrc", "-tAc", query, database],
                extra_env=self.env(conf),
            )
        except ProcessError as exc:
            raise PostgresError(
                f"query failed on database '{database}'",
                hint=exc.result.stderr.strip() or None,
            ) from exc
        return [line for line in result.stdout.splitlines() if line.strip()]
