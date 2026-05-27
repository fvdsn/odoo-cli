import subprocess

import typer

from odoo_cli.odoo import current_workspace
from odoo_cli.postgres import pg_env


def sql(
    query: str = typer.Argument(..., help="SQL query to execute."),
) -> None:
    """Execute a SQL query on the database."""
    workspace = current_workspace()
    config = workspace.config

    db_name = workspace.database_name
    env = pg_env(config)

    result = subprocess.run(
        ["psql", "-d", db_name, "-c", query],
        env=env,
    )
    if result.returncode != 0:
        raise typer.Exit(code=1)


def psql() -> None:
    """Open an interactive PostgreSQL shell on the database."""
    workspace = current_workspace()
    config = workspace.config

    db_name = workspace.database_name
    env = pg_env(config)

    result = subprocess.run(
        ["psql", "-d", db_name],
        env=env,
    )
    if result.returncode != 0:
        raise typer.Exit(code=result.returncode)
