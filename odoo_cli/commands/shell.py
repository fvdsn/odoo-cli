import subprocess

import typer

from odoo_cli.odoo import current_workspace


def shell(
    command: str | None = typer.Option(
        None,
        "--command",
        "-c",
        help="Python code to execute in the Odoo shell context.",
    ),
) -> None:
    """Open a Python shell with the Odoo environment loaded."""
    workspace = current_workspace(require_odoo=True, require_venv=True)
    cmd = workspace.command("shell", f"--config={workspace.odoo_conf}")
    input_text = None
    if command is not None:
        cmd.append("--no-http")
        input_text = command

    result = subprocess.run(cmd, input=input_text, text=command is not None)
    if result.returncode != 0:
        raise typer.Exit(code=result.returncode)
