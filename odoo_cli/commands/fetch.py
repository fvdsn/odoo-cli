"""`odoo fetch`: update the bare repositories from origin."""

from __future__ import annotations

from odoo_cli.cli._click import click
from odoo_cli.cli.context import CliContext


@click.command()
@click.argument("repos", nargs=-1, metavar="[REPO…]")
@click.pass_obj
def fetch(ctx: CliContext, repos: tuple[str, ...]) -> None:
    """Fetch new commits and branches into .repositories from origin.

    Updates every repository (or only the named ones), picking up new branches
    too — e.g. a freshly released version. No worktree is touched; bring a
    worktree's checkouts up to date with `odoo pull`.
    """
    services, out = ctx.services, ctx.output
    workspace = services.workspace.resolve()
    outcomes = services.repositories.fetch(workspace, names=repos or None)

    fetched = [o.name for o in outcomes if o.fetched]
    for o in outcomes:
        if not o.fetched:
            out.warn(f"skipped {o.name}: {o.reason}")
    if fetched:
        out.success(f"fetched {', '.join(fetched)}")
    elif not outcomes:
        out.echo("no repositories to fetch")
