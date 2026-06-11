"""Workspace resolution and creation.

A workspace is identified by the presence of `.repositories/odoo.git`; there
is no marker config file. Resolution order: `ODOO_DIR` if set, else `~/odoo`.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

from odoo_cli.core import paths
from odoo_cli.core.errors import WorkspaceNotFound
from odoo_cli.core.models import Workspace
from odoo_cli.core.odoo_conf import OdooConf, write_defaults


class WorkspaceResolver:
    def __init__(self, env: Mapping[str, str] | None = None):
        self.env: Mapping[str, str] = os.environ if env is None else env

    @property
    def root(self) -> Path:
        return paths.workspace_root(self.env)

    @property
    def conf_path(self) -> Path:
        return paths.odoo_conf_path(self.env)

    def resolve(self) -> Workspace:
        root = self.root
        if not (root / ".repositories" / "odoo.git").is_dir():
            raise WorkspaceNotFound(
                f"no workspace at {root} (missing .repositories/odoo.git)",
                hint="run `odoo init` to create one, or set ODOO_DIR",
            )
        return Workspace(root=root, config=OdooConf.load(self.conf_path))

    def create_skeleton(self) -> Path:
        """Create the workspace directories for `odoo init`. Idempotent; the
        workspace only becomes valid once odoo.git is cloned into it."""
        root = self.root
        for name in (".repositories", ".venvs", ".run"):
            (root / name).mkdir(parents=True, exist_ok=True)
        return root

    def ensure_default_conf(self) -> tuple[bool, list[str]]:
        """Write the default odoo.conf if missing; an existing file is never
        modified. Returns (created, missing_expected_keys)."""
        if self.conf_path.exists():
            return False, OdooConf.load(self.conf_path).missing_defaults()
        write_defaults(self.conf_path)
        return True, []

    def rcfile_warnings(self) -> list[str]:
        """Manual odoo-bin runs resolve ~/.odoorc or ODOO_RC over the shared
        conf; `odoo init` surfaces these (the CLI itself always passes -c)."""
        warnings = []
        home = self.env.get("HOME")
        odoorc = (Path(home) if home else Path.home()) / ".odoorc"
        if odoorc.exists():
            warnings.append(
                f"{odoorc} exists: manual odoo-bin runs will use it instead of "
                f"{self.conf_path}"
            )
        if self.env.get("ODOO_RC"):
            warnings.append(
                "ODOO_RC is set: manual odoo-bin runs will use it instead of "
                f"{self.conf_path}"
            )
        return warnings
