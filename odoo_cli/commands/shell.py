import subprocess

import typer

from odoo_cli.odoo import current_workspace


def shell() -> None:
    """Open an interactive Python shell with the Odoo environment loaded."""
    workspace = current_workspace(require_odoo=True, require_venv=True)
    cmd = workspace.command("shell", f"--config={workspace.odoo_conf}")

    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise typer.Exit(code=result.returncode)


def run(
    code: str = typer.Argument(..., help="Python code to execute in the Odoo environment."),
) -> None:
    """Execute Python code in the Odoo environment."""
    workspace = current_workspace(require_odoo=True, require_venv=True)
    cmd = workspace.command("shell", f"--config={workspace.odoo_conf}", "--no-http")

    result = subprocess.run(cmd, input=code, text=True)
    if result.returncode != 0:
        raise typer.Exit(code=result.returncode)
