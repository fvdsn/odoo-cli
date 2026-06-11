"""`odoo shell`: Python REPL with the Odoo environment, or one-shot -c."""

from __future__ import annotations

from odoo_cli.cli._click import click
from odoo_cli.cli.context import CliContext
from odoo_cli.core.errors import StreamedProcessExit


@click.command()
@click.option("-c", "--code", help="Execute CODE and print its output.")
@click.option("-w", "--worktree", help="Target worktree (default: inferred).")
@click.option("-d", "--db", help="Target database (default: worktree name).")
@click.pass_obj
def shell(
    ctx: CliContext, code: str | None, worktree: str | None, db: str | None
) -> None:
    """Open an interactive shell, or run -c CODE and print the result."""
    target = ctx.services.targets.resolve(worktree=worktree, db=db)
    if code is not None:
        output = ctx.services.shell.execute(target, code)
        if output:
            ctx.output.echo(output.rstrip("\n"))
        return
    exit_code = ctx.services.shell.interactive(target)
    if exit_code != 0:
        raise StreamedProcessExit(exit_code)
