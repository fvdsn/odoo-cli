"""`odoo test`: run module tests against the conventional test database."""

from __future__ import annotations

from odoo_cli.cli._click import click
from odoo_cli.cli.context import CliContext


@click.command()
@click.argument("module_spec", metavar="MODULE")
@click.option(
    "-t", "--tag", "tags", multiple=True,
    help="Test tag or test_ method name (resolved to odoo's format).",
)
@click.option("-w", "--worktree", help="Target worktree (default: inferred).")
@click.option("-d", "--db", help="Target database (default: worktree name).")
@click.pass_obj
def test(
    ctx: CliContext,
    module_spec: str,
    tags: tuple[str, ...],
    worktree: str | None,
    db: str | None,
) -> None:
    """Run tests for MODULE (a module name, `installed`, or `all`).

    Tests run against `{database}-test`, created or reused as needed.
    """
    target = ctx.services.targets.resolve(worktree=worktree, db=db)
    ctx.output.echo(f"Running tests in {target.test_database}...")
    ctx.services.testing.run(target, module_spec, list(tags))
    ctx.output.success("tests passed")
