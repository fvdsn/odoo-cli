"""`odoo update [modules]`: update modules (default: all installed)."""

from __future__ import annotations

from odoo_cli.cli._click import click
from odoo_cli.cli.context import CliContext


@click.command()
@click.argument("modules", nargs=-1)
@click.option("-w", "--worktree", help="Target worktree (default: inferred).")
@click.option("-d", "--db", help="Target database (default: worktree name).")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable outcome.")
@click.pass_obj
def update(
    ctx: CliContext,
    modules: tuple[str, ...],
    worktree: str | None,
    db: str | None,
    as_json: bool,
) -> None:
    """Update modules in the database (no MODULES: update all)."""
    if as_json:
        ctx.output.json_mode = True
    target = ctx.services.targets.resolve(worktree=worktree, db=db)
    ctx.services.modules.update(target, list(modules) or None)
    if as_json:
        ctx.output.json(
            {"updated": list(modules) or "all", "database": target.database}
        )
        return
    ctx.output.success(
        f"updated {', '.join(modules) if modules else 'all modules'} "
        f"in {target.database}"
    )
