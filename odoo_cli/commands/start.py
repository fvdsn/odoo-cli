import subprocess

import typer

from odoo_cli.console import console
from odoo_cli.odoo import current_workspace
from odoo_cli.ports import pid_for_port


def start() -> None:
    """Start the Odoo server."""
    workspace = current_workspace(require_odoo=True, require_venv=True)
    odoo_config = workspace.odoo_config

    # Check ports before starting
    http_port = workspace.http_port
    ws_port = workspace.websocket_port
    blocked = False
    for port, label in [(http_port, "HTTP"), (ws_port, "WebSocket")]:
        pid = pid_for_port(port)
        if pid is not None:
            console.print(f"[red]{label} port {port} is already in use (PID {pid}).[/red]")
            blocked = True
    if blocked:
        raise typer.Exit(code=1)

    cmd = workspace.command(f"--config={workspace.odoo_conf}")

    if odoo_config.get("dev_mode", False):
        cmd.append("--dev=all")

    if not odoo_config.get("demo_data", True):
        cmd.append("--without-demo")

    if odoo_config.get("install_modules"):
        cmd.extend(["-i", ",".join(odoo_config["install_modules"])])

    console.print(f"[dim]$ {' '.join(cmd)}[/dim]\n")

    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        pass
