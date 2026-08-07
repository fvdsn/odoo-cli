"""`odoo pull`: fast-forward a worktree's checkouts to the latest of what they
track."""

from __future__ import annotations

from odoo_cli.cli._click import click
from odoo_cli.cli.context import CliContext
from odoo_cli.core.sync import ADVANCED, SKIPPED, UP_TO_DATE


@click.command()
@click.option("-w", "--worktree", help="Target worktree (default: inferred).")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable outcome.")
@click.pass_obj
def pull(ctx: CliContext, worktree: str | None, as_json: bool) -> None:
    """Fast-forward the worktree's checkouts to the latest of what they track.

    Fetches each checkout's upstream and fast-forwards it. Fast-forward only:
    a checkout that has diverged, is on a branch tracking no version, or has
    uncommitted changes is skipped with guidance, and the rest still pull.
    """
    services, out = ctx.services, ctx.output
    if as_json:
        out.json_mode = True
    target = services.targets.resolve(worktree=worktree)
    result = services.pull.pull(target.workspace, target.worktree)

    if as_json:
        status_names = {ADVANCED: "advanced", UP_TO_DATE: "up_to_date", SKIPPED: "skipped"}
        out.json(
            {
                "worktree": result.worktree,
                "outcomes": [
                    {
                        "repository": o.repo,
                        "status": status_names.get(o.status, str(o.status)),
                        "detail": o.detail,
                        "linked_from": o.linked_from,
                    }
                    for o in result.outcomes
                ],
            }
        )
        return

    out.echo(f"Pulling worktree {result.worktree}...")
    advanced = skipped = 0
    for o in result.outcomes:
        suffix = f" (linked from {o.linked_from})" if o.linked_from else ""
        if o.status == ADVANCED:
            advanced += 1
            out.echo(f"  {o.repo}: {o.detail}{suffix}")
        elif o.status == UP_TO_DATE:
            out.echo(f"  {o.repo}: already up to date{suffix}")
        elif o.status == SKIPPED:
            skipped += 1
            out.warn(f"  skipped {o.repo}: {o.detail}{suffix}")

    if not result.outcomes:
        out.echo("no checkouts to pull")
    elif skipped:
        out.echo(f"{advanced} advanced, {skipped} skipped")
    else:
        out.success("up to date")
