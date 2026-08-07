"""Odoo's per-database filestore location.

v1 passes no --data-dir, so attachments live in odoo-bin's default data
directory (appdirs convention: ~/Library/Application Support/Odoo on macOS,
$XDG_DATA_HOME/Odoo or ~/.local/share/Odoo elsewhere), overridable with the
`data_dir` key in odoo.conf. Database clone/rename keep the filestore in
lockstep; nothing else touches it.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path

from odoo_cli.core.odoo_conf import OdooConf, is_set


def data_dir(
    conf: OdooConf,
    *,
    environ: Mapping[str, str] | None = None,
    platform: str | None = None,
    home: Path | None = None,
) -> Path:
    env = os.environ if environ is None else environ
    value = conf.get("data_dir")
    if is_set(value):
        return Path(value).expanduser()
    base = Path.home() if home is None else home
    if (sys.platform if platform is None else platform) == "darwin":
        return base / "Library" / "Application Support" / "Odoo"
    xdg = env.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg).expanduser() / "Odoo"
    return base / ".local" / "share" / "Odoo"


def filestore_path(conf: OdooConf, database: str, **kwargs) -> Path:
    return data_dir(conf, **kwargs) / "filestore" / database
