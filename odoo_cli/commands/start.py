"""`odoo start`: foreground server (Ctrl-C to stop; lifecycle is v2)."""

from __future__ import annotations

from odoo_cli.cli._click import click
from odoo_cli.cli.context import CliContext
from odoo_cli.core import external_deps
from odoo_cli.core.errors import StreamedProcessExit


@click.command()
@click.option("-w", "--worktree", help="Target worktree (default: inferred).")
@click.option("-d", "--db", help="Target database (default: worktree name).")
@click.option(
    "--new-port",
    is_flag=True,
    help="Reallocate this instance's ports instead of reusing the stored ones.",
)
@click.option(
    "--prod",
    is_flag=True,
    help="Disable dev mode (auto-reload) for this run.",
)
@click.pass_obj
def start(
    ctx: CliContext,
    worktree: str | None,
    db: str | None,
    new_port: bool,
    prod: bool,
) -> None:
    """Start the Odoo server in this terminal."""
    services, out = ctx.services, ctx.output
    target = services.targets.resolve(worktree=worktree, db=db)

    venv = services.venvs.ensure(target.workspace, target.worktree)
    python = services.venvs.python_path(venv.path)

    if services.database.ensure_initialized(target, python=python):
        out.echo(f"Initialized empty database {target.database}")
    else:
        # existing database: the modules it has installed load at boot, so
        # their manifest-declared python deps must be importable (a venv
        # rebuild may have lost them); a fresh db is base-only, nothing to do
        installed = [
            m for m in services.database.installed_modules(target) if m != "base"
        ]
        if installed:
            external_deps.ensure_module_deps(
                services.venvs, services.process, target.worktree, installed,
                venv.path, python,
            )
    if not services.database.installed_applications(target):
        out.hint(
            f"no app is installed in {target.database} yet; install one with "
            "`odoo module install <module>` (e.g. crm)"
        )

    ports = services.server.allocate_ports(target, new_port=new_port)
    command = services.odoo_bin.server_start(
        target, python=python, ports=ports, prod=prod
    )
    out.echo(
        f"Starting Odoo: worktree={target.worktree.name} "
        f"database={target.database}"
    )
    out.echo(f"URL: http://localhost:{ports.http} (gevent: {ports.gevent})")
    out.echo("Ctrl-C to stop")
    code = services.server.run_foreground(command)
    if code not in (0, 130):  # 130: Ctrl-C
        raise StreamedProcessExit(code)
