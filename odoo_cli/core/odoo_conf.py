"""Reader/writer for the shared `odoo.conf` (Odoo's own ini format).

This file holds only workspace-shared, user-editable settings (postgres
connection, dev_mode, without_demo, log_level). Per-instance values
(addons_path, database, ports, data_dir) are computed by services and passed
as CLI args; they are never read from or written here.

Rewriting goes through configparser: unknown keys are preserved, comments and
formatting are not (accepted v1 limitation).
"""

from __future__ import annotations

import configparser
import os
import tempfile
from pathlib import Path

SECTION = "options"

#: Keys whose values are redacted in any listing output.
SECRET_KEYS = frozenset({"db_password", "admin_passwd"})

REDACTED = "********"

#: Defaults written by `odoo init` (usecase.md §1) and the keys init reports
#: as missing when the file already exists.
DEFAULTS: dict[str, str] = {
    "db_host": "False",
    "db_port": "False",
    "db_user": "False",
    "db_password": "False",
    "dev_mode": "all",
    "without_demo": "False",
    "log_level": "warn",
}


class OdooConf:
    def __init__(self, path: Path, parser: configparser.ConfigParser):
        self.path = path
        self._parser = parser

    @classmethod
    def load(cls, path: Path) -> OdooConf:
        """Load the conf; a missing file yields an empty conf (not an error:
        commands other than init still run, odoo-bin applies its defaults)."""
        parser = configparser.ConfigParser()
        if path.exists():
            parser.read(path)
        if not parser.has_section(SECTION):
            parser.add_section(SECTION)
        return cls(path, parser)

    @property
    def exists(self) -> bool:
        return self.path.exists()

    def get(self, key: str) -> str | None:
        return self._parser.get(SECTION, key, fallback=None)

    def set(self, key: str, value: str) -> None:
        self._parser.set(SECTION, key, value)

    def items(self, *, reveal: bool = False) -> dict[str, str]:
        values = dict(self._parser.items(SECTION))
        if not reveal:
            for key in values:
                if key in SECRET_KEYS:
                    values[key] = REDACTED
        return values

    def missing_defaults(self) -> list[str]:
        return [key for key in DEFAULTS if self.get(key) is None]

    def save(self) -> None:
        """Atomic write (temp file + rename) so a crash never truncates the
        user's config."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".odoo.conf.")
        try:
            with os.fdopen(fd, "w") as fh:
                self._parser.write(fh)
            os.replace(tmp, self.path)
        except BaseException:
            os.unlink(tmp)
            raise


def write_defaults(path: Path) -> OdooConf:
    """Create the default conf. Only for a path that does not exist yet —
    `odoo init` never modifies an existing file."""
    conf = OdooConf.load(path)
    for key, value in DEFAULTS.items():
        conf.set(key, value)
    conf.save()
    return conf
