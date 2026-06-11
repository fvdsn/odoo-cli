"""`odoo config`: get/set/list over the shared odoo.conf (wizard is v2)."""

from __future__ import annotations

from odoo_cli.cli._click import click
from odoo_cli.cli.context import CliContext


@click.group()
def config() -> None:
    """Read and edit the shared odoo.conf."""


@config.command()
@click.argument("key")
@click.pass_obj
def get(ctx: CliContext, key: str) -> None:
    """Print one odoo.conf value (secrets included: this is the reveal path)."""
    ctx.output.echo(ctx.services.config.get(key))


@config.command("set")
@click.argument("key")
@click.argument("value")
@click.pass_obj
def set_(ctx: CliContext, key: str, value: str) -> None:
    """Set one odoo.conf value (pure edit, no side effects).

    Unknown keys are preserved, but comments and formatting are rewritten
    by configparser and not preserved.
    """
    ctx.services.config.set(key, value)
    ctx.output.success(f"{key} = {value}")


@config.command("list")
@click.option("--reveal", is_flag=True, help="Show secret values unredacted.")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
@click.pass_obj
def list_(ctx: CliContext, reveal: bool, as_json: bool) -> None:
    """Print the resolved configuration and enabled optional repositories."""
    data = ctx.services.config.list(reveal=reveal)
    if as_json:
        ctx.output.json(data)
        return
    ctx.output.echo(f"# {data['odoo_conf']}")
    for key, value in sorted(data["options"].items()):
        ctx.output.echo(f"{key} = {value}")
    repos = data["repositories"]
    if repos is not None:
        ctx.output.echo(f"# repositories: {', '.join(repos['enabled']) or '(none)'}")
        if repos["available"]:
            ctx.output.echo(
                f"# available via `odoo repo enable`: {', '.join(repos['available'])}"
            )
