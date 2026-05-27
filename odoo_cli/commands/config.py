from pathlib import Path

import typer

from odoo_cli.config import load_config, save_config
from odoo_cli.commands.init import generate_odoo_conf, run_wizard
from odoo_cli.repos import console


def config() -> None:
    """Update the workspace configuration."""
    directory = Path.cwd()

    existing = load_config(directory)
    if not existing:
        console.print("[red]No config.toml found. Run 'odoo-cli init' first.[/red]")
        raise typer.Exit(code=1)

    new_config = run_wizard(existing)
    save_config(directory, new_config)
    console.print(f"\nSaved configuration to [bold]config.toml[/bold]")

    # Regenerate odoo.conf
    generate_odoo_conf(directory, new_config)

    # Print hints for manual steps
    hints = []
    if new_config["version"] != existing.get("version"):
        hints.append("  odoo-cli checkout    # version changed")
    if new_config["repositories"] != existing.get("repositories"):
        hints.append("  odoo-cli init        # repository selection changed, re-run init to clone")
    if new_config.get("ai") != existing.get("ai"):
        hints.append("  odoo-cli ai-setup    # AI harnesses changed")

    if hints:
        console.print("\n[yellow]To apply all changes, run:[/yellow]")
        for hint in hints:
            console.print(hint)
