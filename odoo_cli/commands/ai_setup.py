import typer

from odoo_cli.ai.harnesses import HARNESSES, SETUP_FUNCTIONS
from odoo_cli.console import console
from odoo_cli.workspace import load_workspace_config


def ai_setup() -> None:
    """Generate AI context files and skills for configured harnesses."""
    directory, config = load_workspace_config()

    harnesses = config.get("ai", {}).get("harnesses", [])
    if not harnesses:
        console.print("[yellow]No AI harnesses configured. Run 'odoo-cli init' to set them up.[/yellow]")
        raise typer.Exit(code=1)

    console.print("\n[bold]Setting up AI context files...[/bold]")

    all_files = []
    for harness in harnesses:
        setup_fn = SETUP_FUNCTIONS.get(harness)
        if not setup_fn:
            console.print(f"  [yellow]Unknown harness '{harness}', skipping.[/yellow]")
            continue

        files = setup_fn(directory, config)
        all_files.extend(files)
        console.print(f"  [green]{HARNESSES[harness]}[/green]: {', '.join(files)}")

    console.print(f"\n[green]Generated {len(all_files)} files.[/green]")
