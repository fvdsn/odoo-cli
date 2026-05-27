import typer

from odoo_cli.console import console
from odoo_cli.venv import setup_venv
from odoo_cli.workspace import require_workspace_root


def venv() -> None:
    """Set up (or recreate) the Python virtual environment for Odoo."""
    directory = require_workspace_root()

    odoo_dir = directory / "odoo"
    if not odoo_dir.exists():
        console.print("[red]odoo/ not found. Run 'odoo-cli init' first.[/red]")
        raise typer.Exit(code=1)

    if not setup_venv(directory):
        raise typer.Exit(code=1)
