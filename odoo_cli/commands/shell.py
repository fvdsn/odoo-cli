import subprocess
from pathlib import Path
from typing import Optional

import typer

from odoo_cli.config import load_config
from odoo_cli.repos import console


def shell() -> None:
    """Open an interactive Python shell with the Odoo environment loaded."""
    directory = Path.cwd()

    config = load_config(directory)
    if not config:
        console.print("[red]No config.toml found. Run 'odoo-cli init' first.[/red]")
        raise typer.Exit(code=1)

    odoo_bin = directory / "odoo" / "odoo-bin"
    odoo_conf = directory / "odoo" / "odoo.conf"
    venv_python = directory / "odoo" / ".venv" / "bin" / "python"

    if not odoo_bin.exists():
        console.print("[red]odoo/odoo-bin not found. Run 'odoo-cli init' first.[/red]")
        raise typer.Exit(code=1)

    if not venv_python.exists():
        console.print("[red]odoo/.venv not found. Run 'odoo-cli venv' first.[/red]")
        raise typer.Exit(code=1)

    cmd = [str(venv_python), str(odoo_bin), "shell", f"--config={odoo_conf}"]

    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise typer.Exit(code=result.returncode)


def run(
    code: str = typer.Argument(..., help="Python code to execute in the Odoo environment."),
) -> None:
    """Execute Python code in the Odoo environment."""
    directory = Path.cwd()

    config = load_config(directory)
    if not config:
        console.print("[red]No config.toml found. Run 'odoo-cli init' first.[/red]")
        raise typer.Exit(code=1)

    odoo_bin = directory / "odoo" / "odoo-bin"
    odoo_conf = directory / "odoo" / "odoo.conf"
    venv_python = directory / "odoo" / ".venv" / "bin" / "python"

    if not odoo_bin.exists():
        console.print("[red]odoo/odoo-bin not found. Run 'odoo-cli init' first.[/red]")
        raise typer.Exit(code=1)

    if not venv_python.exists():
        console.print("[red]odoo/.venv not found. Run 'odoo-cli venv' first.[/red]")
        raise typer.Exit(code=1)

    cmd = [str(venv_python), str(odoo_bin), "shell",
           f"--config={odoo_conf}", "--no-http"]

    result = subprocess.run(cmd, input=code, text=True)
    if result.returncode != 0:
        raise typer.Exit(code=result.returncode)
