"""`odoo venv`: rebuild the venv for the current worktree's version."""

from __future__ import annotations

from odoo_cli.cli._click import click
from odoo_cli.cli.context import CliContext


@click.command()
@click.option("-w", "--worktree", help="Target worktree (default: inferred).")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable outcome.")
@click.pass_obj
def venv(ctx: CliContext, worktree: str | None, as_json: bool) -> None:
    """Recreate the virtual environment for the worktree's Odoo version."""
    services, out = ctx.services, ctx.output
    if as_json:
        out.json_mode = True
    target = services.targets.resolve(worktree=worktree)
    out.echo("Rebuilding the virtual environment...")
    result = services.venvs.rebuild(target.workspace, target.worktree)
    if as_json:
        out.json({"venv": str(result.path)})
        return
    out.success(f"venv ready at {result.path}")
