import subprocess

import questionary
import typer

from odoo_cli.console import console
from odoo_cli.odoo import current_workspace
from odoo_cli.postgres import pg_env, terminate_connections


def db_reset() -> None:
    """Drop and recreate the database."""
    workspace = current_workspace()
    config = workspace.config

    db_name = workspace.database_name

    console.print(
        f"\nThis will [bold red]drop[/bold red] the database "
        f"[bold]{db_name}[/bold] and all its data."
    )
    if not questionary.confirm("Are you sure?", default=False).unsafe_ask():
        raise typer.Exit(code=0)

    env = pg_env(config)

    terminate_connections(config, db_name)

    console.print(f"  Dropping [bold]{db_name}[/bold]...", end=" ")
    result = subprocess.run(
        ["dropdb", "--if-exists", db_name],
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        console.print("[red]failed[/red]")
        console.print(f"    [dim]{result.stderr.strip()}[/dim]")
        raise typer.Exit(code=1)
    console.print("[green]done[/green]")

    console.print(f"  Creating [bold]{db_name}[/bold]...", end=" ")
    result = subprocess.run(
        ["createdb", db_name],
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        console.print("[red]failed[/red]")
        console.print(f"    [dim]{result.stderr.strip()}[/dim]")
        raise typer.Exit(code=1)
    console.print("[green]done[/green]")

    # Install configured modules
    odoo_config = workspace.odoo_config
    install_modules = odoo_config.get("install_modules", [])
    if install_modules:
        workspace.require_odoo_checkout()
        workspace.require_venv()

        modules_str = ",".join(install_modules)
        console.print(f"  Installing modules [bold]{modules_str}[/bold]...")

        cmd = workspace.command(
            f"--config={workspace.odoo_conf}",
            "-i",
            modules_str,
            "--stop-after-init",
        )
        if not odoo_config.get("demo_data", True):
            cmd.append("--without-demo")

        console.print(f"  [dim]$ {' '.join(cmd)}[/dim]\n")
        result = subprocess.run(cmd)
        if result.returncode != 0:
            console.print("\n[red]Module installation failed.[/red]")
            raise typer.Exit(code=1)

    console.print(f"\n[green]Database '{db_name}' has been reset and initialized.[/green]")
