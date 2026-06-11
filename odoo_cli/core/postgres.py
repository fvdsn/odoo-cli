"""PostgreSQL access for the CLI's own needs (checks, createdb, SQL).

The connection comes from the `db_*` keys in odoo.conf. Odoo's convention for
"unset" is the string "False"; those keys are simply not exported. The
password travels via PGPASSWORD, never on a command line.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable

from odoo_cli.core.odoo_conf import OdooConf
from odoo_cli.util.process import ProcessRunner

_ENV_KEYS = {
    "db_host": "PGHOST",
    "db_port": "PGPORT",
    "db_user": "PGUSER",
    "db_password": "PGPASSWORD",
}


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
