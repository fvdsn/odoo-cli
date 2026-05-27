import subprocess
from pathlib import Path

import typer

from odoo_cli.config import load_config
from odoo_cli.postgres import pg_env
from odoo_cli.repos import console


def sql(
    query: str = typer.Argument(..., help="SQL query to execute."),
) -> None:
    """Execute a SQL query on the database."""
    directory = Path.cwd()

    config = load_config(directory)
    if not config:
        console.print("[red]No config.toml found. Run 'odoo-cli init' first.[/red]")
        raise typer.Exit(code=1)

    db_name = config["postgres"]["db_name"]
    env = pg_env(config)

    result = subprocess.run(
        ["psql", "-d", db_name, "-c", query],
        env=env,
    )
    if result.returncode != 0:
        raise typer.Exit(code=1)


def psql() -> None:
    """Open an interactive PostgreSQL shell on the database."""
    directory = Path.cwd()

    config = load_config(directory)
    if not config:
        console.print("[red]No config.toml found. Run 'odoo-cli init' first.[/red]")
        raise typer.Exit(code=1)

    db_name = config["postgres"]["db_name"]
    env = pg_env(config)

    result = subprocess.run(
        ["psql", "-d", db_name],
        env=env,
    )
    if result.returncode != 0:
        raise typer.Exit(code=result.returncode)
