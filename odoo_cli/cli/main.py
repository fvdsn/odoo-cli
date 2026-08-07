"""Entry point: click group registration and error translation.

Exit codes: 0 success, 1 user-facing failure, 2 usage error.
"""

from __future__ import annotations

from odoo_cli import __version__, commands
from odoo_cli.cli._click import click
from odoo_cli.cli.context import CliContext
from odoo_cli.core.errors import OdooCliError, ProcessFailed, StreamedProcessExit
from odoo_cli.util.process import ProcessError


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="odoo")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Manage and develop local Odoo instances."""
    if ctx.obj is None:
        ctx.obj = CliContext()


commands.register(cli)


def main(argv: list[str] | None = None) -> int:
    context = CliContext()
    try:
        cli.main(args=argv, standalone_mode=False, obj=context)
        return 0
    except click.exceptions.Abort:
        click.echo("Aborted.", err=True)
        return 130
    except click.exceptions.ClickException as exc:
        exc.show()
        return exc.exit_code
    except StreamedProcessExit as exc:
        # the streamed child already produced its own output
        return exc.code
    except OdooCliError as exc:
        if context.output.json_mode:
            context.output.json({"error": _error_payload(exc)})
        else:
            click.secho(f"error: {exc.message}", fg="red", err=True)
            if exc.hint:
                click.echo(exc.hint, err=True)
        return 1
    except ProcessError as exc:
        # Services translate expected failures; this is the last-resort path.
        if context.output.json_mode:
            context.output.json(
                {
                    "error": {
                        "code": "process_error",
                        "message": str(exc),
                        "stderr": exc.result.stderr.strip() or None,
                    }
                }
            )
        else:
            click.secho(f"error: {exc}", fg="red", err=True)
            if exc.result.stderr:
                click.echo(exc.result.stderr.strip(), err=True)
        return 1


def _error_payload(exc: OdooCliError) -> dict:
    """The JSON error contract: {code, message, hint} plus ProcessFailed's
    subprocess fields when present."""
    payload: dict = {"code": exc.code, "message": exc.message, "hint": exc.hint}
    if isinstance(exc, ProcessFailed):
        payload["argv"] = exc.argv
        payload["returncode"] = exc.returncode
        payload["stderr"] = exc.stderr
    return payload
