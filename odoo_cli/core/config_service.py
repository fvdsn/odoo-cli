"""Backs `odoo config`: a thin, scriptable front over the shared odoo.conf.

Keys are odoo.conf's own flat ini keys — no dotted paths, no translation
layer, no repository keys (enabling a repo is `odoo repo enable`, a clone).
"""

from __future__ import annotations

from odoo_cli.core.errors import OdooCliError, WorkspaceNotFound
from odoo_cli.core.odoo_conf import OdooConf
from odoo_cli.core.repositories import OPTIONAL_REPOS, RepositoryService
from odoo_cli.core.workspace import WorkspaceResolver


class ConfigService:
    def __init__(
        self, workspaces: WorkspaceResolver, repositories: RepositoryService
    ):
        self.workspaces = workspaces
        self.repositories = repositories

    def _conf(self) -> OdooConf:
        return OdooConf.load(self.workspaces.conf_path)

    def get(self, key: str) -> str:
        value = self._conf().get(key)
        if value is None:
            raise OdooCliError(
                f"'{key}' is not set in {self.workspaces.conf_path}",
                hint=f"set it with `odoo config set {key} <value>`",
            )
        return value

    def set(self, key: str, value: str) -> None:
        """Pure ini edit, no side effects. Unknown keys are preserved but
        comments/formatting are not (configparser rewrite)."""
        conf = self._conf()
        conf.set(key, value)
        conf.save()

    def list(self, *, reveal: bool = False) -> dict:
        data: dict = {
            "odoo_conf": str(self.workspaces.conf_path),
            "options": self._conf().items(reveal=reveal),
        }
        try:
            workspace = self.workspaces.resolve()
        except WorkspaceNotFound:
            data["repositories"] = None  # no workspace yet
        else:
            data["repositories"] = {
                "enabled": [r.name for r in self.repositories.list(workspace)],
                "available": [
                    name
                    for name in OPTIONAL_REPOS
                    if not self.repositories.exists(workspace, name)
                ],
            }
        return data
