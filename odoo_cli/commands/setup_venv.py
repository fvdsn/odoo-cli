from pathlib import Path

import typer

from odoo_cli.repos import console, setup_venv


def venv() -> None:
    """Set up (or recreate) the Python virtual environment for Odoo."""
    directory = Path.cwd()

    odoo_dir = directory / "odoo"
    if not odoo_dir.exists():
        console.print("[red]odoo/ not found. Run 'odoo-cli init' first.[/red]")
        raise typer.Exit(code=1)

    if not setup_venv(directory):
        raise typer.Exit(code=1)
