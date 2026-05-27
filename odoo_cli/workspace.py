"""Workspace configuration helpers."""

from pathlib import Path

import typer

from odoo_cli.config import load_config
from odoo_cli.console import console


def load_required_config(directory: Path) -> dict:
    """Load config.toml or exit with a consistent CLI error."""
    config = load_config(directory)
    if not config:
        console.print("[red]No config.toml found. Run 'odoo-cli init' first.[/red]")
        raise typer.Exit(code=1)
    return config
