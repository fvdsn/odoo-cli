import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import typer

from odoo_cli.console import console
from odoo_cli.odoo import current_workspace
from odoo_cli.ports import pid_for_port
from odoo_cli.postgres import check_connection, pg_env, sql_literal
from odoo_cli.repos import get_repo_status, get_repos
from odoo_cli.venv import get_min_python_version


@dataclass
class DoctorResult:
    errors: int = 0
    warnings: int = 0

    def ok(self, message: str) -> None:
        console.print(f"  [green]OK[/green] {message}")

    def warn(self, message: str, fix: str | None = None) -> None:
        self.warnings += 1
        console.print(f"  [yellow]WARN[/yellow] {message}")
        if fix:
            console.print(f"    [dim]Fix: {fix}[/dim]")

    def error(self, message: str, fix: str | None = None) -> None:
        self.errors += 1
        console.print(f"  [red]ERR[/red] {message}")
        if fix:
            console.print(f"    [dim]Fix: {fix}[/dim]")


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def database_exists(config: dict, db_name: str) -> bool | None:
    if not command_exists("psql"):
        return None

    result = subprocess.run(
        [
            "psql",
            "-d",
            "postgres",
            "-tAc",
            f"SELECT 1 FROM pg_database WHERE datname = {sql_literal(db_name)}",
        ],
        capture_output=True,
        text=True,
        env=pg_env(config),
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() == "1"


def python_version(python: Path) -> str | None:
    result = subprocess.run(
        [str(python), "--version"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return (result.stdout or result.stderr).strip().removeprefix("Python ")


def doctor() -> None:
    """Check the current Odoo development workspace for common setup problems."""
    workspace = current_workspace()
    config = workspace.config
    result = DoctorResult()

    console.print("[bold]Workspace[/bold]")
    result.ok(f"Found workspace root: {workspace.directory}")
    if workspace.odoo_dir.exists():
        result.ok("odoo/ directory exists")
    else:
        result.error("odoo/ directory is missing", "run `odoo init` from the workspace root")

    if workspace.odoo_bin.exists():
        result.ok("odoo/odoo-bin exists")
    else:
        result.error("odoo/odoo-bin is missing", "run `odoo init` to clone repositories")

    if workspace.odoo_conf.exists():
        result.ok("odoo/odoo.conf exists")
    else:
        result.warn("odoo/odoo.conf is missing", "run `odoo config` or `odoo init`")

    console.print("\n[bold]Tools[/bold]")
    for command in ["git", "uv", "psql", "dropdb", "createdb", "lsof"]:
        if command_exists(command):
            result.ok(f"{command} is available")
        else:
            result.error(
                f"{command} is not available",
                f"install `{command}` and ensure it is on PATH",
            )

    console.print("\n[bold]Python[/bold]")
    min_python = get_min_python_version(workspace.directory)
    if min_python:
        result.ok(f"Odoo requires Python {min_python}")
    else:
        result.warn("Could not determine Odoo's minimum Python version")

    if workspace.venv_python.exists():
        venv_version = python_version(workspace.venv_python)
        if venv_version:
            if min_python and not venv_version.startswith(min_python):
                result.warn(
                    f"venv uses Python {venv_version}, expected {min_python}",
                    "run `odoo venv`",
                )
            else:
                result.ok(f"venv uses Python {venv_version}")
        else:
            result.warn("Could not read venv Python version", "run `odoo venv`")
    else:
        result.error("odoo/.venv is missing", "run `odoo venv`")

    console.print("\n[bold]PostgreSQL[/bold]")
    if command_exists("psql"):
        try:
            ok, error = check_connection(config["postgres"])
        except (OSError, subprocess.SubprocessError) as exc:
            ok, error = False, str(exc)
        if ok:
            result.ok("Can connect to PostgreSQL")
            db_exists = database_exists(config, workspace.database_name)
            if db_exists is True:
                result.ok(f"Database exists: {workspace.database_name}")
            elif db_exists is False:
                result.warn(
                    f"Database does not exist: {workspace.database_name}",
                    "run `odoo db-reset`",
                )
            else:
                result.warn("Could not check configured database")
        else:
            result.error("Cannot connect to PostgreSQL", f"{error}; run `odoo config`")
    else:
        result.error("Cannot check PostgreSQL because psql is missing")

    console.print("\n[bold]Ports[/bold]")
    for port, label in [
        (workspace.http_port, "HTTP"),
        (workspace.websocket_port, "WebSocket"),
    ]:
        pid = pid_for_port(port)
        if pid is None:
            result.ok(f"{label} port {port} is free")
        else:
            result.warn(f"{label} port {port} is in use by PID {pid}")

    console.print("\n[bold]Repositories[/bold]")
    for name, _url, dest in get_repos(workspace.directory, config):
        if not dest.exists():
            if name == "odoo":
                result.error("odoo repository is missing", "run `odoo init`")
            else:
                result.warn(f"{name} repository is not cloned")
            continue

        status = get_repo_status(dest)
        branch = status["branch"] or "unknown"
        if status["dirty"]:
            result.warn(f"{name}: branch {branch} has uncommitted changes")
        elif status["ahead"] > 0:
            result.warn(f"{name}: branch {branch} has {status['ahead']} unpushed commit(s)")
        else:
            result.ok(f"{name}: branch {branch}, clean")

    console.print(f"\n[bold]Summary:[/bold] {result.errors} error(s), {result.warnings} warning(s)")
    if result.errors:
        raise typer.Exit(code=1)
