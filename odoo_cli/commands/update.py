import subprocess

import typer

from odoo_cli.console import console
from odoo_cli.odoo import current_workspace


def update(
    modules: str | None = typer.Argument(
        None,
        help="Comma-separated modules to update (default: all).",
    ),
) -> None:
    """Update module(s) in the database without starting the server."""
    workspace = current_workspace(require_odoo=True, require_venv=True)

    target = modules or "all"

    cmd = workspace.command(
        f"--config={workspace.odoo_conf}",
        "-u",
        target,
        "--stop-after-init",
    )

    console.print(f"Updating [bold]{target}[/bold]...")
    console.print(f"[dim]$ {' '.join(cmd)}[/dim]\n")

    result = subprocess.run(cmd)
    if result.returncode != 0:
        console.print(f"\n[red]Update failed (exit code {result.returncode}).[/red]")
        raise typer.Exit(code=1)

    console.print("\n[green]Update complete.[/green]")
