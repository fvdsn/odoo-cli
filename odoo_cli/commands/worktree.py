"""`odoo worktree create`: full and linked worktrees (list/remove are v2)."""

from __future__ import annotations

from odoo_cli.cli._click import click
from odoo_cli.cli.context import CliContext
from odoo_cli.core.errors import VersionNotFound


@click.group()
def worktree() -> None:
    """Worktree operations."""


@worktree.command()
@click.argument("name")
@click.argument("version", required=False)
@click.option(
    "--linked-from",
    metavar="WORKTREE",
    help="Create a linked worktree: symlink standard repos from WORKTREE.",
)
@click.option(
    "--addon",
    "addons",
    multiple=True,
    metavar="REPOSITORY",
    help="Check out an added repository at the worktree root (repeatable, "
    "requires --linked-from).",
)
@click.pass_obj
def create(
    ctx: CliContext,
    name: str,
    version: str | None,
    linked_from: str | None,
    addons: tuple[str, ...],
) -> None:
    """Create worktree NAME on VERSION.

    With a single argument, the name is also the version and must resolve
    to an Odoo ref (`odoo worktree create 19.0`, `... master`).
    """
    services, out = ctx.services, ctx.output
    if addons and not linked_from:
        raise click.UsageError("--addon requires --linked-from")
    single_argument = version is None
    version = version or name
    workspace = services.workspace.resolve()

    try:
        if linked_from:
            result = services.worktrees.create_linked(
                workspace, name, version, linked_from, list(addons)
            )
        else:
            result = services.worktrees.create_full(workspace, name, version)
    except VersionNotFound as exc:
        if single_argument and exc.hint is None:
            exc.hint = (
                f"'{name}' does not resolve to an Odoo version; use "
                "`odoo worktree create NAME VERSION` to name a worktree freely"
            )
        raise

    if result.existed:
        out.echo(f"worktree {name} already exists; added only what was missing")
    for repo_name in result.linked:
        out.echo(f"linked {repo_name} from {linked_from}")
    for repo_name in result.checked_out:
        out.echo(f"checked out {repo_name}")
    for skipped in result.skipped:
        out.warn(f"skipped {skipped.name}: {skipped.reason}")
    for warning in result.warnings:
        out.warn(warning)

    out.echo("Setting up the virtual environment...")
    services.venvs.ensure(workspace, result.worktree)
    out.success(f"worktree {name} ready at {result.worktree.path}")
    out.echo(f"Next: cd {result.worktree.path} && odoo start")
