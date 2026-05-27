"""Shared AI context setup workflow."""

from pathlib import Path

from odoo_cli.ai.harnesses import HARNESSES, SETUP_FUNCTIONS
from odoo_cli.console import console


def configured_harnesses(config: dict) -> list[str]:
    return config.get("ai", {}).get("harnesses", [])


def setup_ai_contexts(directory: Path, config: dict) -> list[str]:
    """Generate AI context files for the configured harnesses."""
    all_files = []
    for harness in configured_harnesses(config):
        setup_fn = SETUP_FUNCTIONS.get(harness)
        if not setup_fn:
            console.print(f"  [yellow]Unknown harness '{harness}', skipping.[/yellow]")
            continue

        files = setup_fn(directory, config)
        all_files.extend(files)
        console.print(f"  [green]{HARNESSES[harness]}[/green]: {', '.join(files)}")

    return all_files
