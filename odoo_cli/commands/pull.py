import subprocess
from pathlib import Path

import typer

from odoo_cli.config import load_config
from odoo_cli.repos import console, get_repos


def pull() -> None:
    """Pull latest changes from origin across all repositories."""
    directory = Path.cwd()

    config = load_config(directory)
    if not config:
        console.print("[red]No config.toml found. Run 'odoo-cli init' first.[/red]")
        raise typer.Exit(code=1)

    repos = get_repos(directory, config)

    for name, _url, dest in repos:
        if not dest.exists():
            console.print(f"  [yellow]{name}/[/yellow] not found, skipping.")
            continue

        console.print(f"  Pulling [bold]{name}[/bold]...", end=" ")
        result = subprocess.run(
            ["git", "-C", str(dest), "pull", "--ff-only"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            console.print("[red]failed[/red]")
            console.print(f"    [dim]{stderr}[/dim]")
        elif "Already up to date" in result.stdout:
            console.print("[dim]up to date[/dim]")
        else:
            # Show a short summary of what changed
            lines = result.stdout.strip().splitlines()
            summary = lines[-1] if lines else "updated"
            console.print(f"[green]{summary}[/green]")
