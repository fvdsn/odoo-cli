"""`odoo worktree create`, `odoo worktree remove`, `odoo worktree list`."""

from __future__ import annotations

from odoo_cli.cli._click import click
from odoo_cli.cli.context import CliContext
from odoo_cli.core import agent_assets
from odoo_cli.core.errors import OdooCliError, PostgresError, VersionNotFound
from odoo_cli.core.worktrees import discover, infer_base_version


@click.group()
def worktree() -> None:
    """Worktree operations."""


@worktree.command(name="list")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
@click.pass_obj
def list_(ctx: CliContext, as_json: bool) -> None:
    """List the workspace's worktrees."""
    services, out = ctx.services, ctx.output
    if as_json:
        out.json_mode = True
    workspace = services.workspace.resolve()

    entries = []
    for wt in discover(workspace):
        try:
            version: str | None = services.worktrees.detect_version(wt)
        except (OdooCliError, OSError):
            version = None  # broken checkout still deserves a row
        entries.append(
            {
                "name": wt.name,
                "path": str(wt.path),
                "linked_from": wt.linked_from,
                "version": version,
                "valid": services.worktrees.is_valid(wt),
                "repos": services.worktrees.checkouts(wt),
            }
        )

    if as_json:
        out.json({"worktrees": entries})
        return
    if not entries:
        out.echo("no worktrees")
        return
    for entry in entries:
        notes = []
        if entry["linked_from"]:
            notes.append(f"linked from {entry['linked_from']}")
        if not entry["valid"]:
            notes.append("invalid")
        suffix = f" ({', '.join(notes)})" if notes else ""
        out.echo(f"{entry['name']}  {entry['version'] or '?'}  {entry['path']}{suffix}")


@worktree.command()
@click.argument("name")
@click.argument("source", required=False, metavar="[SOURCE]")
@click.option(
    "--linked",
    is_flag=True,
    help="Share SOURCE's checkouts through symlinks instead of branching; "
    "SOURCE must be an existing worktree.",
)
@click.option(
    "--addon",
    "addons",
    multiple=True,
    metavar="REPOSITORY",
    help="Check out an added repository at the worktree root (repeatable, "
    "requires --linked).",
)
@click.option(
    "--empty-db",
    is_flag=True,
    help="Do not copy the source worktree's database; the new worktree's "
    "database is created empty on first start.",
)
@click.option("--json", "as_json", is_flag=True, help="Machine-readable outcome.")
@click.pass_obj
def create(
    ctx: CliContext,
    name: str,
    source: str | None,
    linked: bool,
    addons: tuple[str, ...],
    empty_db: bool,
    as_json: bool,
) -> None:
    """Create worktree NAME from SOURCE.

    Every repo gets a branch NAME starting at SOURCE: a version
    (`odoo worktree create fix-pos 19.0`) or an existing worktree to
    duplicate (`odoo worktree create customer-b customer-a`) — every repo
    the source worktree has, addons included, branches from the source's
    checkouts; duplicating a linked worktree yields another linked
    worktree on the same original. With a single argument, the name is
    also the source and must resolve to an Odoo ref
    (`odoo worktree create 19.0`, `... master`).

    With --linked, SOURCE names an existing worktree whose checkouts are
    shared through symlinks (`odoo worktree create customer-a 19.0
    --linked`); only --addon repositories get real checkouts.

    When SOURCE is an existing worktree with an initialized database, the
    new worktree's database is created from it as a template (filestore
    included), so its installed modules need no reinstall; --empty-db
    skips the copy.
    """
    services, out = ctx.services, ctx.output
    if as_json:
        out.json_mode = True
    if addons and not linked:
        raise click.UsageError("--addon requires --linked")
    if linked and source is None:
        raise click.UsageError(
            "--linked needs a source worktree: "
            "`odoo worktree create NAME SOURCE --linked`"
        )
    single_argument = source is None
    if single_argument:
        # `odoo worktree create 19.0-my-feature` infers base 19.0 from the
        # version prefix (odoo/odoo branch convention); a name without a version
        # prefix stays the source/ref, as before.
        source = infer_base_version(name) or name
    inferred_base = single_argument and source != name
    workspace = services.workspace.resolve()
    # a worktree source wins over a ref of the same name; both readings
    # coincide for version-named worktrees
    source_is_worktree = (
        source != name and (workspace.root / source / "odoo").exists()
    )

    try:
        if linked:
            result = services.worktrees.create_linked(
                workspace, name, source, list(addons)
            )
        elif source_is_worktree:
            result = services.worktrees.create_duplicate(workspace, name, source)
        else:
            result = services.worktrees.create_full(workspace, name, source)
    except VersionNotFound as exc:
        # only nudge toward `NAME VERSION` when the name wasn't a version prefix;
        # an inferred base that doesn't resolve speaks for itself
        if single_argument and not inferred_base and exc.hint is None:
            exc.hint = (
                f"'{name}' does not resolve to an Odoo version; use "
                "`odoo worktree create NAME VERSION` to name a worktree freely, "
                "or prefix the name with a version (`19.0-my-feature`)"
            )
        raise

    if result.existed:
        out.echo(f"worktree {name} already exists; added only what was missing")
    # a duplicated linked worktree links to the source's original, not the source
    link_source = result.worktree.linked_from or source
    for repo_name in result.linked:
        out.echo(f"linked {repo_name} from {link_source}")
    for repo_name in result.checked_out:
        out.echo(f"checked out {repo_name}")
    for skipped in result.skipped:
        out.warn(f"skipped {skipped.name}: {skipped.reason}")
    for warning in result.warnings:
        out.warn(warning)

    # a worktree created from another worktree starts from its database;
    # best-effort: without a usable source database (or postgres at all)
    # the empty-on-first-start rule applies as before
    seeded_from = None
    if not empty_db and (linked or source_is_worktree):
        try:
            if services.database.seed_from(workspace, source, name):
                seeded_from = source
                out.echo(f"created database {name} from {source}")
        except (PostgresError, OSError) as exc:
            out.warn(f"could not copy database {source} to {name}: {exc}")

    out.echo("Setting up the virtual environment...")
    venv = services.venvs.ensure(workspace, result.worktree)
    try:  # best-effort: a thin AGENTS.md for an agent started in this worktree
        agent_assets.write_worktree_docs(result.worktree)
    except OSError as exc:
        out.warn(f"could not write agent context: {exc}")
    if as_json:
        out.json(
            {
                "worktree": name,
                "path": str(result.worktree.path),
                "existed": result.existed,
                "linked": list(result.linked),
                "checked_out": list(result.checked_out),
                "skipped": [
                    {"repository": s.name, "reason": s.reason} for s in result.skipped
                ],
                "warnings": list(result.warnings),
                "database_seeded_from": seeded_from,
                "venv": str(venv.path),
            }
        )
        return
    out.success(f"worktree {name} ready at {result.worktree.path}")
    out.echo(f"Next: cd {result.worktree.path} && odoo start")


@worktree.command()
@click.argument("name")
@click.option("--drop-db", is_flag=True, help="Also drop the worktree's database(s).")
@click.option(
    "--delete-branches",
    is_flag=True,
    help="Delete the per-worktree feature branches (never a shared version "
    "branch); kept by default so committed work survives.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Skip the safety checks (uncommitted changes, unmerged branches, a "
    "running server).",
)
@click.option(
    "--purge",
    is_flag=True,
    help="Remove everything: implies --drop-db --delete-branches --force.",
)
@click.option("--json", "as_json", is_flag=True, help="Machine-readable outcome.")
@click.pass_obj
def remove(
    ctx: CliContext,
    name: str,
    drop_db: bool,
    delete_branches: bool,
    force: bool,
    purge: bool,
    as_json: bool,
) -> None:
    """Remove worktree NAME.

    Deletes the worktree directory and frees its git registrations and run
    state. By default the per-worktree branches and the database are kept, and
    removal refuses when there is work to lose — uncommitted changes, branches
    with unmerged commits (only when --delete-branches), or a running server —
    or when other worktrees are linked from this one.

    --purge bundles --drop-db --delete-branches --force to wipe everything; it
    still refuses on linked dependents (remove those first).
    """
    services, out = ctx.services, ctx.output
    if as_json:
        out.json_mode = True
    if purge:
        drop_db = delete_branches = force = True
    workspace = services.workspace.resolve()
    result = services.worktrees.remove(
        workspace,
        name,
        drop_db=drop_db,
        delete_branches=delete_branches,
        force=force,
    )
    if as_json:
        out.json(
            {
                "worktree": name,
                "removed_path": str(result.removed_path),
                "deleted_branches": list(result.deleted_branches),
                "dropped_databases": list(result.dropped_databases),
            }
        )
        return
    for branch in result.deleted_branches:
        out.echo(f"deleted branch {branch}")
    for db in result.dropped_databases:
        out.echo(f"dropped database {db}")
    out.success(f"removed worktree {name} ({result.removed_path})")


worktree.add_command(remove, name="rm")
