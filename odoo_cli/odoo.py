"""Odoo workspace paths and command helpers."""

from dataclasses import dataclass
from pathlib import Path

import typer

from odoo_cli.console import console
from odoo_cli.workspace import load_workspace_config


@dataclass(frozen=True)
class OdooWorkspace:
    directory: Path
    config: dict

    @property
    def odoo_dir(self) -> Path:
        return self.directory / "odoo"

    @property
    def odoo_bin(self) -> Path:
        return self.odoo_dir / "odoo-bin"

    @property
    def odoo_conf(self) -> Path:
        return self.odoo_dir / "odoo.conf"

    @property
    def venv_python(self) -> Path:
        return self.odoo_dir / ".venv" / "bin" / "python"

    @property
    def odoo_config(self) -> dict:
        return self.config.get("odoo", {})

    @property
    def database_name(self) -> str:
        return self.config["postgres"]["db_name"]

    @property
    def http_port(self) -> int:
        return self.odoo_config.get("http_port", 8069)

    @property
    def websocket_port(self) -> int:
        return self.odoo_config.get("websocket_port", 8072)

    def require_odoo_checkout(self) -> None:
        if not self.odoo_bin.exists():
            console.print("[red]odoo/odoo-bin not found. Run 'odoo-cli init' first.[/red]")
            raise typer.Exit(code=1)

    def require_venv(self) -> None:
        if not self.venv_python.exists():
            console.print("[red]odoo/.venv not found. Run 'odoo-cli venv' first.[/red]")
            raise typer.Exit(code=1)

    def command(self, *args: str) -> list[str]:
        return [str(self.venv_python), str(self.odoo_bin), *args]


def current_workspace(*, require_odoo: bool = False, require_venv: bool = False) -> OdooWorkspace:
    """Return the current Odoo workspace, optionally validating runtime paths."""
    directory, config = load_workspace_config()
    workspace = OdooWorkspace(directory, config)
    if require_odoo:
        workspace.require_odoo_checkout()
    if require_venv:
        workspace.require_venv()
    return workspace


def configured_addons_paths(
    directory: Path,
    config: dict,
    *,
    only_existing: bool = True,
) -> list[Path]:
    """Return addons paths for the configured repository layout."""
    from odoo_cli.repos import get_repos

    paths = [directory / "odoo" / "addons"]
    for name, _url, dest in get_repos(directory, config):
        if name in {"odoo", "documentation"}:
            continue
        if not only_existing or dest.exists():
            paths.append(dest)
    return paths
