"""`odoo init`: bootstrap the workspace. Minimal, good defaults, unattended.

Installs no module: the initial database is created empty by the first
command that needs it (`odoo module install`, `odoo start`).
"""

from __future__ import annotations

from pathlib import Path

from odoo_cli.cli._click import click
from odoo_cli.cli.context import CliContext
from odoo_cli.core.models import Workspace, Worktree
from odoo_cli.core.odoo_conf import OdooConf
from odoo_cli.core.repositories import DEFAULT_REPOS
from odoo_cli.util.process import ProcessError


@click.command()
@click.argument("version", required=False)
@click.option(
    "--full",
    is_flag=True,
    help="Complete clones instead of blobless (--filter=blob:none).",
)
@click.option(
    "--no-demo-data",
    is_flag=True,
    help="Disable demo data (sets without_demo in odoo.conf).",
)
@click.pass_obj
def init(ctx: CliContext, version: str | None, full: bool, no_demo_data: bool) -> None:
    """Create the workspace: clone repos, first worktree, venv, odoo.conf.

    With no VERSION, uses the latest stable (highest N.0 branch).
    """
    services, out = ctx.services, ctx.output

    # fail fast before any slow clone
    if not services.postgres.is_installed():
        plan = services.postgres.install_plan()
        out.echo(f"PostgreSQL is not installed; installing with {plan.manager}...")
        result = services.postgres.install()
        out.echo(f"Installed PostgreSQL with {result.manager}")
        for warning in result.warnings:
            out.warn(warning)

    root = services.workspace.create_skeleton()

    created, missing = services.workspace.ensure_default_conf()
    conf_path = services.workspace.conf_path
    if created:
        out.echo(f"Wrote default configuration to {conf_path}")
    elif missing:
        out.warn(
            f"{conf_path} exists and was left untouched; expected keys missing: "
            f"{', '.join(missing)} (use `odoo config set`)"
        )
    for warning in services.workspace.rcfile_warnings():
        out.warn(warning)

    if no_demo_data:
        conf = OdooConf.load(conf_path)
        conf.set("without_demo", "True")
        conf.save()

    # the workspace only resolves once odoo.git exists; build the value
    # object directly for the bootstrap clones
    bootstrap = Workspace(root=root, config=OdooConf.load(conf_path))
    clone_mode = services.repositories.clone_mode(full)
    for name in DEFAULT_REPOS:
        if services.repositories.is_corrupt(bootstrap, name):
            action = "Recloning (incomplete)"
        elif services.repositories.exists(bootstrap, name):
            action = "Fetching"
        else:
            action = "Cloning"
        out.echo(f"{action} {name} ({clone_mode})...")
        try:
            services.repositories.clone_or_fetch(bootstrap, name, full=full)
        except ProcessError:
            if action != "Fetching":
                raise
            # the repo is already usable; a re-run must not require network
            out.warn(f"could not fetch {name} (offline?); using the local copy")

    workspace = services.workspace.resolve()
    odoo_repo = services.repositories.get(workspace, "odoo")
    version = version or services.repositories.latest_stable_version(odoo_repo)

    def create_initial_worktree() -> Worktree:
        out.echo(f"Preparing worktree {version}...")
        try:
            result = services.worktrees.create_full(workspace, version, version)
        except ProcessError as exc:
            if full or not _is_promisor_failure(exc):
                raise
            repo_name = _failing_repo_name(exc) or "odoo"
            out.warn(
                f"blobless {repo_name} checkout failed while fetching missing "
                "objects; retrying with a full clone"
            )
            services.repositories.replace_with_clone(
                workspace,
                repo_name,
                odoo_repo.url if repo_name == "odoo" else None,
                full=True,
            )
            result = services.worktrees.create_full(workspace, version, version)
        if result.existed:
            out.echo(
                f"Worktree {version} already exists; added only what was missing"
            )
        for warning in result.warnings:
            out.warn(warning)
        for skipped in result.skipped:
            out.warn(f"skipped {skipped.name}: {skipped.reason}")
        return result.worktree

    # create_full converges on re-runs: it completes a valid worktree,
    # repairs the leftover of an interrupted run, and refuses (with a
    # move-it-aside hint) anything it cannot prove to be its own
    worktree = create_initial_worktree()

    out.echo("Setting up the virtual environment...")
    services.venvs.ensure(workspace, worktree)

    if not services.postgres.check_connection(workspace.config):
        out.warn(
            "could not connect to PostgreSQL; fix the db_* keys with "
            "`odoo config set db_user ...` (see `odoo config list`)"
        )

    out.success(f"Workspace ready at {workspace.root}")
    out.echo(f"Next: cd {worktree.path} && odoo start")


def _is_promisor_failure(exc: ProcessError) -> bool:
    output = f"{exc.result.stdout}\n{exc.result.stderr}".lower()
    return "promisor remote" in output or "partial clone" in output


def _failing_repo_name(exc: ProcessError) -> str | None:
    """Repository name from a failed `git -C <repo>.git ...` invocation."""
    argv = exc.result.argv
    if len(argv) >= 3 and argv[:2] == ("git", "-C"):
        name = Path(argv[2]).name
        if name.endswith(".git"):
            return name.removesuffix(".git")
    return None
