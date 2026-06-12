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
@click.argument("source", required=False, metavar="[SOURCE]")
@click.option(
    "--linked",
    is_flag=True,
    help="Share SOURCE's checkouts through symlinks instead of branching; "
    "SOURCE must be an existing worktree.",
)
@click.option(
    "--addon",
    "addons",
    multiple=True,
    metavar="REPOSITORY",
    help="Check out an added repository at the worktree root (repeatable, "
    "requires --linked).",
)
@click.pass_obj
def create(
    ctx: CliContext,
    name: str,
    source: str | None,
    linked: bool,
    addons: tuple[str, ...],
) -> None:
    """Create worktree NAME from SOURCE.

    Every repo gets a branch NAME starting at SOURCE, a version
    (`odoo worktree create fix-pos 19.0`). With a single argument, the
    name is also the source and must resolve to an Odoo ref
    (`odoo worktree create 19.0`, `... master`).

    With --linked, SOURCE names an existing worktree whose checkouts are
    shared through symlinks (`odoo worktree create customer-a 19.0
    --linked`); only --addon repositories get real checkouts.
    """
    services, out = ctx.services, ctx.output
    if addons and not linked:
        raise click.UsageError("--addon requires --linked")
    if linked and source is None:
        raise click.UsageError(
            "--linked needs a source worktree: "
            "`odoo worktree create NAME SOURCE --linked`"
        )
    single_argument = source is None
    source = source or name
    workspace = services.workspace.resolve()

    try:
        if linked:
            result = services.worktrees.create_linked(
                workspace, name, source, list(addons)
            )
        else:
            result = services.worktrees.create_full(workspace, name, source)
    except VersionNotFound as exc:
        if exc.hint is None:
            if single_argument:
                exc.hint = (
                    f"'{name}' does not resolve to an Odoo version; use "
                    "`odoo worktree create NAME VERSION` to name a worktree "
                    "freely"
                )
            elif (workspace.root / source / "odoo").exists():
                exc.hint = (
                    f"'{source}' is a worktree; share its checkouts with "
                    f"`odoo worktree create {name} {source} --linked` "
                    "(duplicating a worktree is not supported yet)"
                )
        raise

    if result.existed:
        out.echo(f"worktree {name} already exists; added only what was missing")
    for repo_name in result.linked:
        out.echo(f"linked {repo_name} from {source}")
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
