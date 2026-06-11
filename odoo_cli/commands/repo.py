"""`odoo repo`: manage the bare repositories under `.repositories/`."""

from __future__ import annotations

from odoo_cli.cli._click import click
from odoo_cli.cli.context import CliContext
from odoo_cli.core import worktrees as worktrees_mod
from odoo_cli.core.errors import RepositoryNotFound
from odoo_cli.core.repositories import OPTIONAL_REPOS


@click.group()
def repo() -> None:
    """Repository operations."""


@repo.command()
@click.argument("name")
@click.argument("url")
@click.option("--full", is_flag=True, help="Complete clone instead of blobless.")
@click.pass_obj
def add(ctx: CliContext, name: str, url: str, full: bool) -> None:
    """Clone an additional addon repository into the workspace.

    Adding a repository does not modify existing worktrees; check it out
    with `odoo worktree create --addon`.
    """
    workspace = ctx.services.workspace.resolve()
    mode = ctx.services.repositories.clone_mode(full)
    ctx.output.echo(f"Cloning {name} ({mode})...")
    spec = ctx.services.repositories.add(workspace, name, url, full=full)
    ctx.output.success(f"added repository {spec.name} ({spec.url})")


@repo.command()
@click.argument("name")
@click.argument("url", required=False)
@click.option(
    "--future-only",
    is_flag=True,
    help="Clone/fetch only; leave existing worktrees untouched.",
)
@click.option(
    "--to",
    "to",
    multiple=True,
    metavar="WORKTREE",
    help="Add only to the listed worktrees (repeatable).",
)
@click.pass_obj
def enable(
    ctx: CliContext,
    name: str,
    url: str | None,
    future_only: bool,
    to: tuple[str, ...],
) -> None:
    """Enable a built-in optional repository (enterprise, themes, upgrade).

    By default the repo is added to all compatible existing worktrees;
    incompatible versions are skipped with a warning.
    """
    services, out = ctx.services, ctx.output
    if name not in OPTIONAL_REPOS:
        raise RepositoryNotFound(
            f"'{name}' is not an optional built-in repository",
            hint=f"choose from: {', '.join(OPTIONAL_REPOS)}; custom repos use "
            "`odoo repo add`",
        )
    workspace = services.workspace.resolve()
    existed = services.repositories.exists(workspace, name)
    out.echo(f"{'Fetching' if existed else 'Cloning'} {name}...")
    services.repositories.clone_or_fetch(workspace, name, url)

    added, skipped = [], []
    if not future_only:
        available = {wt.name: wt for wt in worktrees_mod.discover(workspace)}
        names = to or tuple(sorted(available))
        for wt_name in names:
            if wt_name not in available:
                skipped.append((wt_name, "no such worktree"))
                continue
            result = services.worktrees.add_repository(
                workspace, available[wt_name], name
            )
            if result.added:
                added.append(wt_name)
            else:
                skipped.append((wt_name, result.reason))

    out.success(f"{name} {'fetched' if existed else 'cloned'}")
    if added:
        out.echo(f"added to: {', '.join(added)}")
    for wt_name, reason in skipped:
        out.warn(f"skipped {wt_name}: {reason}")
    if future_only:
        out.echo("existing worktrees untouched (--future-only)")
