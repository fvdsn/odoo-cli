"""PostgreSQL access for the CLI's own needs (checks, createdb, SQL).

The connection comes from the `db_*` keys in odoo.conf. Odoo's convention for
"unset" is the string "False"; those keys are simply not exported. The
password travels via PGPASSWORD, never on a command line.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable

from odoo_cli.core.errors import PostgresError
from odoo_cli.core.odoo_conf import OdooConf
from odoo_cli.util.process import ProcessError, ProcessRunner

_ENV_KEYS = {
    "db_host": "PGHOST",
    "db_port": "PGPORT",
    "db_user": "PGUSER",
    "db_password": "PGPASSWORD",
}


def quote_literal(value: str) -> str:
    """SQL string literal with quotes doubled. Names reaching this module are
    already validated (TargetResolver), this is the second line of defense."""
    return "'" + value.replace("'", "''") + "'"


class PostgresService:
    def __init__(
        self,
        runner: ProcessRunner,
        which: Callable[[str], str | None] = shutil.which,
    ):
        self.runner = runner
        self.which = which

    def env(self, conf: OdooConf) -> dict[str, str]:
        env = {}
        for key, var in _ENV_KEYS.items():
            value = conf.get(key)
            if value and value != "False":
                env[var] = value
        return env

    def is_installed(self) -> bool:
        return self.which("psql") is not None

    def check_connection(self, conf: OdooConf) -> bool:
        result = self.runner.run(
            ["psql", "--no-psqlrc", "-tAc", "SELECT 1", "postgres"],
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
