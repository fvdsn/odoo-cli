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

from odoo_cli.core.errors import OdooCliError

SECTION = "options"

#: Keys whose values are redacted in any listing output.
SECRET_KEYS = frozenset({"db_password", "admin_passwd"})

REDACTED = "********"


def is_set(value: str | None) -> bool:
    """Odoo's convention: the string "False" (or nothing) means unset."""
    return bool(value) and value != "False"


#: odoo's `_check_bool` falsy spellings (tools/config.py).
_FALSE_VALUES = frozenset({"0", "no", "false", "off"})


def demo_enabled(conf: OdooConf | None) -> bool:
    """Whether odoo-bin installs demo data in a new database under this conf.

    Mirrors odoo >= 19: demo is off by default; conf's `without_demo` is
    parsed with `_check_bool` and inverted into with_demo. So only an
    explicit falsy `without_demo` (the `odoo init` default "False") enables
    demo. Callers of `db init` need this spelled out because that subcommand
    only honors its own `--with-demo` flag, never the conf."""
    if conf is None:
        return False
    value = conf.get("without_demo")
    return value is not None and value.strip().lower() in _FALSE_VALUES

#: Defaults written by `odoo init` (usecase.md §1) and the keys init reports
#: as missing when the file already exists. The postgres connection keys
#: (db_host, db_port, db_user, db_password) are deliberately not written:
#: absent already means "local defaults", and odoo-bin warns on every run
#: about non-boolean options holding the literal string "False". They are
#: added by `odoo config set` (or init's port detection) when needed.
DEFAULTS: dict[str, str] = {
    "dev_mode": "all",
    "without_demo": "False",
    "log_level": "warn",
}


class OdooConf:
    def __init__(self, path: Path, parser: configparser.RawConfigParser):
        self.path = path
        self._parser = parser

    @classmethod
    def load(cls, path: Path) -> OdooConf:
        """Load the conf; a missing file yields an empty conf (not an error:
        commands other than init still run, odoo-bin applies its defaults).

        RawConfigParser matches odoo-bin's own parser: `%` has no special
        meaning, so values like a password containing `%` stay legal.

        A hand-edit that breaks the ini syntax must not take down every
        command with a parser traceback — `odoo config set` is the repair
        tool and has to keep working."""
        parser = configparser.RawConfigParser()
        if path.exists():
            try:
                parser.read(path)
            except configparser.Error as exc:
                reason = exc.message.splitlines()[0]  # ParsingError is multi-line
                raise OdooCliError(
                    f"could not parse {path}: {reason}",
                    hint="fix the file by hand, or delete it and re-run `odoo init`",
                ) from exc
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
            for key, value in values.items():
                # an unset secret is not a secret
                if key in SECRET_KEYS and is_set(value):
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
