import subprocess
from pathlib import Path

import typer

from odoo_cli.config import load_config
from odoo_cli.repos import console


def check_port(port: int) -> int | None:
    """Check if a port is in use. Returns the PID using it, or None."""
    result = subprocess.run(
        ["lsof", "-ti", f"tcp:{port}"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return int(result.stdout.strip().splitlines()[0])
    return None


def start() -> None:
    """Start the Odoo server."""
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

    odoo_config = config.get("odoo", {})

    # Check ports before starting
    http_port = odoo_config.get("http_port", 8069)
    ws_port = odoo_config.get("websocket_port", 8072)
    blocked = False
    for port, label in [(http_port, "HTTP"), (ws_port, "WebSocket")]:
        pid = check_port(port)
        if pid is not None:
            console.print(f"[red]{label} port {port} is already in use (PID {pid}).[/red]")
            blocked = True
    if blocked:
        raise typer.Exit(code=1)

    cmd = [str(venv_python), str(odoo_bin), f"--config={odoo_conf}"]

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
