"""`odoo update [modules]`: update modules (default: all installed)."""

from __future__ import annotations

from odoo_cli.cli._click import click
from odoo_cli.cli.context import CliContext


@click.command()
@click.argument("modules", nargs=-1)
@click.option("-w", "--worktree", help="Target worktree (default: inferred).")
@click.option("-d", "--db", help="Target database (default: worktree name).")
@click.pass_obj
def update(
    ctx: CliContext, modules: tuple[str, ...], worktree: str | None, db: str | None
) -> None:
    """Update modules in the database (no MODULES: update all)."""
    target = ctx.services.targets.resolve(worktree=worktree, db=db)
    ctx.services.modules.update(target, list(modules) or None)
    ctx.output.success(
        f"updated {', '.join(modules) if modules else 'all modules'} "
        f"in {target.database}"
    )
