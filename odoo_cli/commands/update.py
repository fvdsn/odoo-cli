import subprocess
from pathlib import Path
from typing import Optional

import typer

from odoo_cli.config import load_config
from odoo_cli.repos import console


def update(
    modules: Optional[str] = typer.Argument(
        None,
        help="Comma-separated modules to update (default: all).",
    ),
) -> None:
    """Update module(s) in the database without starting the server."""
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

    target = modules or "all"

    cmd = [
        str(venv_python), str(odoo_bin),
        f"--config={odoo_conf}",
        "-u", target,
        "--stop-after-init",
    ]

    console.print(f"Updating [bold]{target}[/bold]...")
    console.print(f"[dim]$ {' '.join(cmd)}[/dim]\n")

    result = subprocess.run(cmd)
    if result.returncode != 0:
        console.print(f"\n[red]Update failed (exit code {result.returncode}).[/red]")
        raise typer.Exit(code=1)

    console.print(f"\n[green]Update complete.[/green]")
