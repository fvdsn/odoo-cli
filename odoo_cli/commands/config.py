from odoo_cli.config import save_config
from odoo_cli.console import console
from odoo_cli.odoo_conf import generate_odoo_conf
from odoo_cli.wizard import run_wizard
from odoo_cli.workspace import load_workspace_config


def config() -> None:
    """Update the workspace configuration."""
    directory, existing = load_workspace_config()

    new_config = run_wizard(existing)
    save_config(directory, new_config)
    console.print("\nSaved configuration to [bold]config.toml[/bold]")

    # Regenerate odoo.conf
    generate_odoo_conf(directory, new_config)

    # Print hints for manual steps
    hints = []
    if new_config["version"] != existing.get("version"):
        hints.append("  odoo checkout    # version changed")
    if new_config["repositories"] != existing.get("repositories"):
        hints.append("  odoo init        # repository selection changed, re-run init to clone")
    if new_config.get("ai") != existing.get("ai"):
        hints.append("  odoo ai-setup    # AI harnesses changed")

    if hints:
        console.print("\n[yellow]To apply all changes, run:[/yellow]")
        for hint in hints:
            console.print(hint)
