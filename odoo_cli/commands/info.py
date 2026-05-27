from pathlib import Path

import typer

from odoo_cli.config import load_config
from odoo_cli.repos import console


def info() -> None:
    """Show current workspace configuration."""
    directory = Path.cwd()

    config = load_config(directory)
    if not config:
        console.print("[red]No config.toml found. Run 'odoo-cli init' first.[/red]")
        raise typer.Exit(code=1)

    odoo_config = config.get("odoo", {})
    pg = config["postgres"]

    print(f"Version: {config.get('version', 'unknown')}")
    print(f"Database: {pg['db_name']}")
    print(f"HTTP port: {odoo_config.get('http_port', 8069)}")
    print(f"WebSocket port: {odoo_config.get('websocket_port', 8072)}")
    print(f"Dev mode: {odoo_config.get('dev_mode', False)}")
    print(f"Demo data: {odoo_config.get('demo_data', True)}")
    print(f"Data dir: {odoo_config.get('data_dir', '~/.local/share/Odoo')}")
    print(f"Installed modules: {', '.join(odoo_config.get('install_modules', []))}")

    repos = config.get("repositories", {})
    active = ["odoo"]
    if repos.get("enterprise"):
        active.append("enterprise")
    if repos.get("documentation"):
        active.append("documentation")
    if repos.get("themes"):
        active.append("themes")
    for url in repos.get("extra_addons", []):
        name = url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
        active.append(f"addons/{name}")
    print(f"Repositories: {', '.join(active)}")
