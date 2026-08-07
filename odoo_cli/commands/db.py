"""`odoo db`: database lifecycle (reset, list, clone, rename)."""

from __future__ import annotations

from odoo_cli.cli._click import click
from odoo_cli.cli.context import CliContext


@click.group()
def db() -> None:
    """Database operations."""


@db.command()
@click.option("-w", "--worktree", help="Target worktree (default: inferred).")
@click.option("-d", "--db", "database", help="Target database (default: worktree name).")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable outcome.")
@click.pass_obj
def reset(
    ctx: CliContext, worktree: str | None, database: str | None, as_json: bool
) -> None:
    """Drop and recreate the database, reinstalling its current modules.

    The installed module set is read from the database itself; a database
    that never had modules is recreated empty.
    """
    services, out = ctx.services, ctx.output
    if as_json:
        out.json_mode = True
    target = services.targets.resolve(worktree=worktree, db=database)
    venv = services.venvs.ensure(target.workspace, target.worktree)
    python = services.venvs.python_path(venv.path)
    # announce the set before dropping: if the reset is interrupted, the
    # list (which lives only in the database being dropped) is on screen
    to_reinstall = services.database.resettable_modules(target)
    if to_reinstall:
        out.echo(f"will reinstall after reset: {', '.join(to_reinstall)}")
    reinstalled = services.database.reset(target, python=python)
    if as_json:
        out.json({"database": target.database, "reinstalled": reinstalled})
        return
    if reinstalled:
        out.success(
            f"reset {target.database}, reinstalled: {', '.join(reinstalled)}"
        )
    else:
        out.success(f"reset {target.database} (empty)")


@db.command(name="list")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
@click.pass_obj
def list_(ctx: CliContext, as_json: bool) -> None:
    """List databases with size, owner and Odoo version."""
    services, out = ctx.services, ctx.output
    if as_json:
        out.json_mode = True
    workspace = services.workspace.resolve()
    entries = services.database.list_databases(workspace)
    if as_json:
        out.json({"databases": entries})
        return
    if not entries:
        out.echo("no databases")
        return
    for entry in entries:
        size = f"{entry['size_bytes'] / 1_000_000:.0f} MB"
        version = entry["version"] or "not an Odoo database"
        out.echo(f"{entry['name']}  {size}  {version}")


@db.command()
@click.argument("source")
@click.argument("target")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable outcome.")
@click.pass_obj
def clone(ctx: CliContext, source: str, target: str, as_json: bool) -> None:
    """Copy database SOURCE to TARGET, filestore included.

    Open connections on SOURCE are terminated (PostgreSQL cannot copy a
    database with active sessions); a server using it will reconnect.
    """
    services, out = ctx.services, ctx.output
    if as_json:
        out.json_mode = True
    workspace = services.workspace.resolve()
    copied = services.database.clone(workspace, source, target)
    if as_json:
        out.json({"source": source, "database": target, "filestore_copied": copied})
        return
    out.success(f"cloned {source} to {target}" + (" (with filestore)" if copied else ""))


@db.command()
@click.argument("old")
@click.argument("new")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable outcome.")
@click.pass_obj
def rename(ctx: CliContext, old: str, new: str, as_json: bool) -> None:
    """Rename database OLD to NEW, moving its filestore along."""
    services, out = ctx.services, ctx.output
    if as_json:
        out.json_mode = True
    workspace = services.workspace.resolve()
    moved = services.database.rename(workspace, old, new)
    if as_json:
        out.json({"database": new, "renamed_from": old, "filestore_moved": moved})
        return
    out.success(f"renamed {old} to {new}" + (" (with filestore)" if moved else ""))
