"""`odoo db`: database lifecycle (v1: reset only; shell/query are v2)."""

from __future__ import annotations

from odoo_cli.cli._click import click
from odoo_cli.cli.context import CliContext


@click.group()
def db() -> None:
    """Database operations."""


@db.command()
@click.option("-w", "--worktree", help="Target worktree (default: inferred).")
@click.option("-d", "--db", "database", help="Target database (default: worktree name).")
@click.pass_obj
def reset(ctx: CliContext, worktree: str | None, database: str | None) -> None:
    """Drop and recreate the database, reinstalling its current modules.

    The installed module set is read from the database itself; a database
    that never had modules is recreated empty.
    """
    services, out = ctx.services, ctx.output
    target = services.targets.resolve(worktree=worktree, db=database)
    venv = services.venvs.ensure(target.workspace, target.worktree)
    python = services.venvs.python_path(venv.path)
    # announce the set before dropping: if the reset is interrupted, the
    # list (which lives only in the database being dropped) is on screen
    to_reinstall = services.database.resettable_modules(target)
    if to_reinstall:
        out.echo(f"will reinstall after reset: {', '.join(to_reinstall)}")
    reinstalled = services.database.reset(target, python=python)
    if reinstalled:
        out.success(
            f"reset {target.database}, reinstalled: {', '.join(reinstalled)}"
        )
    else:
        out.success(f"reset {target.database} (empty)")
