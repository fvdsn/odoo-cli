from pathlib import Path

import typer

from odoo_cli.config import load_config, save_config
from odoo_cli.console import console
from odoo_cli.git_utils import add_dev_remote, clone_repo
from odoo_cli.odoo_conf import generate_odoo_conf
from odoo_cli.repos import get_repos
from odoo_cli.venv import setup_venv
from odoo_cli.wizard import run_wizard


def apply_config(directory: Path, config: dict) -> None:
    repos = get_repos(directory, config)

    addons_dir = directory / "addons"
    extra_addons = config["repositories"].get("extra_addons", [])
    if extra_addons and not addons_dir.exists():
        addons_dir.mkdir()

    version = config["version"]
    user_name = config["user"]["name"]
    user_email = config["user"]["email"]

    console.print("\n[bold]Cloning repositories...[/bold]")
    for name, url, dest in repos:
        ok = clone_repo(name, url, dest, version, user_name, user_email)
        if not ok:
            raise typer.Exit(code=1)

    dev_url = config["remotes"]["dev_url"]
    console.print("\n[bold]Setting up dev remote...[/bold]")
    for name, _url, dest in repos:
        if dest.exists():
            add_dev_remote(dest, name, dev_url)
            console.print(f"  [dim]{name}[/dim] → odoo-dev remote configured")

    console.print("\n[bold]Setting up Python environment...[/bold]")
    if not setup_venv(directory):
        raise typer.Exit(code=1)

    generate_odoo_conf(directory, config)

    # AI context setup
    if config.get("ai", {}).get("harnesses"):
        from odoo_cli.ai.harnesses import SETUP_FUNCTIONS, HARNESSES
        console.print("\n[bold]Setting up AI context files...[/bold]")
        for harness in config["ai"]["harnesses"]:
            setup_fn = SETUP_FUNCTIONS.get(harness)
            if setup_fn:
                files = setup_fn(directory, config)
                console.print(f"  [green]{HARNESSES[harness]}[/green]: {', '.join(files)}")

    console.print("\n[green]Workspace initialized successfully.[/green]")


def init(
    directory: Path = typer.Argument(
        ".",
        help="Directory to initialize the Odoo workspace in.",
    ),
) -> None:
    """Initialize an Odoo development workspace."""
    directory = directory.resolve()

    if not directory.exists():
        directory.mkdir(parents=True)
        console.print(f"Created directory [bold]{directory}[/bold]")

    config = load_config(directory)
    if config:
        console.print(f"Found [bold]config.toml[/bold] in {directory}, skipping wizard.")
    else:
        config = run_wizard()
        save_config(directory, config)
        console.print(f"\nSaved configuration to [bold]{directory}/config.toml[/bold]")

    apply_config(directory, config)
