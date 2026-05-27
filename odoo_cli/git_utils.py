"""Git helpers for workspace repository setup."""

import subprocess
from pathlib import Path

from odoo_cli.console import console
from odoo_cli.repos import resolve_branch


def configure_git_user(repo_dir: Path, name: str, email: str) -> None:
    for key, value in [("user.name", name), ("user.email", email)]:
        subprocess.run(
            ["git", "-C", str(repo_dir), "config", key, value],
            check=True,
        )


def clone_repo(
    name: str,
    url: str,
    dest: Path,
    branch: str,
    user_name: str,
    user_email: str,
) -> bool:
    if dest.exists():
        console.print(f"  [yellow]{name}/[/yellow] already exists, skipping.")
        configure_git_user(dest, user_name, user_email)
        return True

    actual_branch = resolve_branch(url, branch)
    if actual_branch is None:
        console.print(f"  [red]{name}: no valid branch for '{branch}', skipping.[/red]")
        return False
    if actual_branch != branch:
        console.print(
            f"  [yellow]{name}: branch '{branch}' not found, "
            f"falling back to '{actual_branch}'[/yellow]"
        )

    console.print(f"  Cloning [bold]{name}[/bold] ([dim]{actual_branch}[/dim])...")
    try:
        subprocess.run(
            [
                "git",
                "clone",
                "--branch",
                actual_branch,
                "-c",
                f"user.name={user_name}",
                "-c",
                f"user.email={user_email}",
                url,
                str(dest),
            ],
            check=True,
        )
        return True
    except subprocess.CalledProcessError:
        console.print(f"  [red]Failed to clone {name}.[/red]")
        return False


def add_dev_remote(repo_dir: Path, repo_name: str, dev_url_template: str) -> None:
    url = dev_url_template.format(repo=repo_name)
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "remote"],
        capture_output=True,
        text=True,
    )
    if "odoo-dev" in result.stdout.splitlines():
        return
    subprocess.run(
        ["git", "-C", str(repo_dir), "remote", "add", "odoo-dev", url],
        check=True,
    )
