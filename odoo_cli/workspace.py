"""Workspace configuration helpers."""

from pathlib import Path

import typer

from odoo_cli.config import config_path, load_config
from odoo_cli.console import console


WORKSPACE_CONFIG_KEYS = {"repositories", "postgres", "odoo"}


def is_workspace_config(config: dict) -> bool:
    """Return whether a parsed config looks like an odoo-cli workspace config."""
    return WORKSPACE_CONFIG_KEYS.issubset(config)


def find_workspace_root(start: Path | None = None) -> Path | None:
    """Find the nearest parent containing an odoo-cli config.toml."""
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent

    for directory in (current, *current.parents):
        if not config_path(directory).exists():
            continue
        config = load_config(directory)
        if config and is_workspace_config(config):
            return directory

    return None


def require_workspace_root(start: Path | None = None) -> Path:
    """Find the workspace root or exit with a consistent CLI error."""
    directory = find_workspace_root(start)
    if directory is None:
        console.print("[red]No config.toml found in this directory or its parents. Run 'odoo-cli init' first.[/red]")
        raise typer.Exit(code=1)
    return directory


def load_required_config(directory: Path) -> dict:
    """Load config.toml or exit with a consistent CLI error."""
    config = load_config(directory)
    if not config or not is_workspace_config(config):
        console.print("[red]No config.toml found. Run 'odoo-cli init' first.[/red]")
        raise typer.Exit(code=1)
    return config


def load_workspace_config(start: Path | None = None) -> tuple[Path, dict]:
    """Find the workspace root and load its config."""
    directory = require_workspace_root(start)
    return directory, load_required_config(directory)
