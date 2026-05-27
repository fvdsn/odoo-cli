import subprocess
from pathlib import Path

import typer

from odoo_cli.config import load_config
from odoo_cli.repos import console, get_repos


def get_branch(repo_path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def check_port(port: int) -> int | None:
    """Return the PID using the port, or None."""
    result = subprocess.run(
        ["lsof", "-ti", f"tcp:{port}"],
        capture_output=True, text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return int(result.stdout.strip().splitlines()[0])
    return None


def info() -> None:
    """Show current workspace configuration."""
    directory = Path.cwd()

    config = load_config(directory)
    if not config:
        console.print("[red]No config.toml found. Run 'odoo-cli init' first.[/red]")
        raise typer.Exit(code=1)

    odoo_config = config.get("odoo", {})
    pg = config["postgres"]
    http_port = odoo_config.get("http_port", 8069)

    # Server status
    pid = check_port(http_port)
    if pid:
        print(f"Server: running (PID {pid})")
    else:
        print(f"Server: not running")

    print(f"URL: http://localhost:{http_port}")
    admin_user = odoo_config.get("admin_user", "admin")
    admin_password = odoo_config.get("admin_password", "admin")
    print(f"Admin credentials: {admin_user} / {admin_password}")
    print(f"Version: {config.get('version', 'unknown')}")
    print(f"Database: {pg['db_name']}")
    print(f"HTTP port: {http_port}")
    print(f"WebSocket port: {odoo_config.get('websocket_port', 8072)}")
    print(f"Dev mode: {odoo_config.get('dev_mode', False)}")
    print(f"Demo data: {odoo_config.get('demo_data', True)}")
    print(f"Data dir: {odoo_config.get('data_dir', '~/.local/share/Odoo')}")
    print(f"Installed modules: {', '.join(odoo_config.get('install_modules', []))}")

    print(f"\nRepositories:")
    for name, _url, dest in get_repos(directory, config):
        if dest.exists():
            branch = get_branch(dest)
            print(f"  {name}: {branch}")
        else:
            print(f"  {name}: (not cloned)")
