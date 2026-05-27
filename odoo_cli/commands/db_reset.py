import subprocess
from pathlib import Path

import questionary
import typer

from odoo_cli.config import load_config
from odoo_cli.postgres import pg_env, terminate_connections
from odoo_cli.repos import console


def db_reset() -> None:
    """Drop and recreate the database."""
    directory = Path.cwd()

    config = load_config(directory)
    if not config:
        console.print("[red]No config.toml found. Run 'odoo-cli init' first.[/red]")
        raise typer.Exit(code=1)

    db_name = config["postgres"]["db_name"]

    console.print(f"\nThis will [bold red]drop[/bold red] the database [bold]{db_name}[/bold] and all its data.")
    if not questionary.confirm("Are you sure?", default=False).unsafe_ask():
        raise typer.Exit(code=0)

    env = pg_env(config)

    terminate_connections(config, db_name)

    console.print(f"  Dropping [bold]{db_name}[/bold]...", end=" ")
    result = subprocess.run(
        ["dropdb", "--if-exists", db_name],
        capture_output=True, text=True, env=env,
    )
    if result.returncode != 0:
        console.print("[red]failed[/red]")
        console.print(f"    [dim]{result.stderr.strip()}[/dim]")
        raise typer.Exit(code=1)
    console.print("[green]done[/green]")

    console.print(f"  Creating [bold]{db_name}[/bold]...", end=" ")
    result = subprocess.run(
        ["createdb", db_name],
        capture_output=True, text=True, env=env,
    )
    if result.returncode != 0:
        console.print("[red]failed[/red]")
        console.print(f"    [dim]{result.stderr.strip()}[/dim]")
        raise typer.Exit(code=1)
    console.print("[green]done[/green]")

    # Install configured modules
    odoo_config = config.get("odoo", {})
    install_modules = odoo_config.get("install_modules", [])
    if install_modules:
        odoo_bin = directory / "odoo" / "odoo-bin"
        odoo_conf = directory / "odoo" / "odoo.conf"
        venv_python = directory / "odoo" / ".venv" / "bin" / "python"

        modules_str = ",".join(install_modules)
        console.print(f"  Installing modules [bold]{modules_str}[/bold]...")

        cmd = [
            str(venv_python), str(odoo_bin),
            f"--config={odoo_conf}",
            "-i", modules_str,
            "--stop-after-init",
        ]
        if not odoo_config.get("demo_data", True):
            cmd.append("--without-demo")

        console.print(f"  [dim]$ {' '.join(cmd)}[/dim]\n")
        result = subprocess.run(cmd)
        if result.returncode != 0:
            console.print(f"\n[red]Module installation failed.[/red]")
            raise typer.Exit(code=1)

    console.print(f"\n[green]Database '{db_name}' has been reset and initialized.[/green]")
