from typing import Optional

import questionary
import typer

from odoo_cli.config import save_config
from odoo_cli.console import console
from odoo_cli.repos import (
    branch_exists,
    check_repos_before_switch,
    checkout_version,
    get_available_versions,
    REPOS,
)
from odoo_cli.workspace import load_workspace_config


def checkout(
    version: Optional[str] = typer.Argument(
        None,
        help="Version to switch to (e.g. 19.0, saas-19.3, master).",
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y",
        help="Skip confirmation for feature branch warnings. "
             "Still fails on uncommitted changes or unpushed commits.",
    ),
) -> None:
    """Checkout a version branch across all repositories."""
    directory, config = load_workspace_config()

    if version is None:
        if yes:
            console.print("[red]Version argument is required when using --yes.[/red]")
            raise typer.Exit(code=1)
        versions = get_available_versions()
        version = questionary.select(
            "Odoo version:",
            choices=versions,
        ).unsafe_ask()

    # Validate against odoo remote
    if not branch_exists(REPOS["odoo"], version):
        console.print(f"[red]Version '{version}' does not exist on odoo/odoo.[/red]")
        raise typer.Exit(code=1)

    # Safety checks
    dirty, on_feature_branch, unpushed = check_repos_before_switch(directory, config)

    if dirty:
        console.print("\n[red bold]Repos with uncommitted changes (blocking):[/red bold]")
        for name, branch in dirty:
            console.print(f"  [red]•[/red] {name} (on {branch})")
        console.print("\nPlease commit or stash your changes before switching.")
        raise typer.Exit(code=1)

    if unpushed:
        console.print("\n[red bold]Repos with unpushed commits (blocking):[/red bold]")
        for name, count in unpushed:
            console.print(f"  [red]•[/red] {name} ({count} commit{'s' if count > 1 else ''} ahead)")
        console.print("\nPlease push your commits before switching.")
        raise typer.Exit(code=1)

    if on_feature_branch:
        console.print("\n[yellow bold]Repos on feature branches:[/yellow bold]")
        for name, branch in on_feature_branch:
            console.print(f"  [yellow]•[/yellow] {name} → {branch}")
        console.print("\nSwitching will move these repos off their feature branches.")

        if not yes:
            if not questionary.confirm("\nProceed anyway?", default=False).unsafe_ask():
                raise typer.Exit(code=0)

    old_version = config.get("version")
    config["version"] = version
    save_config(directory, config)

    console.print(f"\nSwitching from [dim]{old_version}[/dim] to [bold]{version}[/bold]\n")
    checkout_version(directory, config, version)

    console.print(f"\n[green]All repositories switched to {version}.[/green]")
    console.print("[dim]Run 'odoo-cli venv' if you need to update the Python environment.[/dim]")
