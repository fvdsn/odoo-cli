"""`odoo module install`: install modules into the current database."""

from __future__ import annotations

from odoo_cli.cli._click import click
from odoo_cli.cli.context import CliContext


@click.group()
def module() -> None:
    """Module operations."""


@module.command()
@click.argument("modules", nargs=-1, required=True)
@click.option("-w", "--worktree", help="Target worktree (default: inferred).")
@click.option("-d", "--db", help="Target database (default: worktree name).")
@click.pass_obj
def install(
    ctx: CliContext, modules: tuple[str, ...], worktree: str | None, db: str | None
) -> None:
    """Install one or more modules (creates the database if needed)."""
    target = ctx.services.targets.resolve(worktree=worktree, db=db)
    ctx.services.modules.install(target, list(modules))
    ctx.output.success(
        f"installed {', '.join(modules)} in {target.database}"
    )
