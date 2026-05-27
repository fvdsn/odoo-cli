import subprocess
from pathlib import Path

from odoo_cli.odoo import current_workspace
from odoo_cli.ports import pid_for_port
from odoo_cli.repos import get_repos


def get_branch(repo_path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def info() -> None:
    """Show current workspace configuration."""
    workspace = current_workspace()
    directory = workspace.directory
    config = workspace.config

    odoo_config = workspace.odoo_config
    pg = config["postgres"]
    http_port = workspace.http_port

    pid = pid_for_port(http_port)
    if pid:
        print(f"Server: running (PID {pid})")
    else:
        print("Server: not running")

    print(f"URL: http://localhost:{http_port}")
    admin_user = odoo_config.get("admin_user", "admin")
    admin_password = odoo_config.get("admin_password", "admin")
    print(f"Admin credentials: {admin_user} / {admin_password}")
    print(f"Version: {config.get('version', 'unknown')}")
    print(f"Database: {pg['db_name']}")
    print(f"HTTP port: {http_port}")
    print(f"WebSocket port: {workspace.websocket_port}")
    print(f"Dev mode: {odoo_config.get('dev_mode', False)}")
    print(f"Demo data: {odoo_config.get('demo_data', True)}")
    print(f"Data dir: {odoo_config.get('data_dir', '~/.local/share/Odoo')}")
    print(f"Installed modules: {', '.join(odoo_config.get('install_modules', []))}")

    print("\nRepositories:")
    for name, _url, dest in get_repos(directory, config):
        if dest.exists():
            branch = get_branch(dest)
            print(f"  {name}: {branch}")
        else:
            print(f"  {name}: (not cloned)")
