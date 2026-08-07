"""`odoo where`: show exactly what the CLI inferred for this context.

The shared odoo.conf plus the printed command IS the running configuration,
so this is the canonical way to inspect or reproduce a CLI run manually.
"""

from __future__ import annotations

from odoo_cli.cli._click import click
from odoo_cli.cli.context import CliContext
from odoo_cli.core.addons import resolve_addons_paths
from odoo_cli.core.odoo_conf import OdooConf, is_set


@click.command()
@click.option("-w", "--worktree", help="Target worktree (default: inferred).")
@click.option("-d", "--db", help="Target database (default: worktree name).")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
@click.pass_obj
def where(ctx: CliContext, worktree: str | None, db: str | None, as_json: bool) -> None:
    """Show the resolved workspace, worktree, database, venv and command."""
    services, out = ctx.services, ctx.output
    if as_json:
        out.json_mode = True
    target = services.targets.resolve(worktree=worktree, db=db)

    venv_path = services.venvs.venv_path(target.workspace, target.worktree)
    python = services.venvs.python_path(venv_path)
    ports = services.server.preview_ports(target)
    stored = services.server.store.read_ports(target) is not None
    command = services.odoo_bin.server_start(target, python=python, ports=ports)
    conf = OdooConf.load(services.workspace.conf_path)

    data = {
        "workspace": str(target.workspace.root),
        "worktree": target.worktree.name,
        "worktree_path": str(target.worktree.path),
        "linked_from": target.worktree.linked_from,
        "version": services.worktrees.detect_version(target.worktree),
        "database": target.database,
        "venv": str(venv_path),
        "python": str(python),
        "odoo_bin": str(target.worktree.odoo_path / "odoo-bin"),
        "odoo_conf": str(services.workspace.conf_path),
        "addons_path": [str(p) for p in resolve_addons_paths(target.worktree)],
        "ports": {"http": ports.http, "gevent": ports.gevent, "reserved": stored},
        "command": command.redacted_argv,
        # the full run contract: an external supervisor can spawn the server
        # from these four fields without re-deriving anything
        "cwd": str(command.cwd),
        "env": command.env,
        # connection facts a caller needs before the server is up; the
        # password stays in odoo_conf (path above), never in output.
        # Odoo's "False means unset" convention maps to null
        "postgres": {
            key: conf.get(f"db_{key}") if is_set(conf.get(f"db_{key}")) else None
            for key in ("host", "port", "user")
        },
    }
    if as_json:
        out.json(data)
        return

    out.echo(f"workspace:   {data['workspace']}")
    worktree_line = data["worktree"]
    if data["linked_from"]:
        worktree_line += f" (linked from {data['linked_from']})"
    out.echo(f"worktree:    {worktree_line}")
    out.echo(f"version:     {data['version']}")
    out.echo(f"database:    {data['database']}")
    out.echo(f"venv:        {data['venv']}")
    out.echo(f"odoo.conf:   {data['odoo_conf']}")
    out.echo(f"addons path: {', '.join(data['addons_path'])}")
    ports_note = "" if stored else " (estimate; allocated on first start)"
    out.echo(f"ports:       http={ports.http} gevent={ports.gevent}{ports_note}")
    out.echo(f"command:     {' '.join(data['command'])}")
