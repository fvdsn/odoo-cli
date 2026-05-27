import typer

from odoo_cli.ai.setup import configured_harnesses, setup_ai_contexts
from odoo_cli.console import console
from odoo_cli.workspace import load_workspace_config


def ai_setup() -> None:
    """Generate AI context files and skills for configured harnesses."""
    directory, config = load_workspace_config()

    if not configured_harnesses(config):
        console.print("[yellow]No AI harnesses configured. Run 'odoo-cli init' to set them up.[/yellow]")
        raise typer.Exit(code=1)

    console.print("\n[bold]Setting up AI context files...[/bold]")

    all_files = setup_ai_contexts(directory, config)
    console.print(f"\n[green]Generated {len(all_files)} files.[/green]")
