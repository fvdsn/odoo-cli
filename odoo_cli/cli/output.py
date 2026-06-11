"""Terminal rendering helpers. Default verbosity stays low (one line beats
ten); machine output goes through `json` from structured result objects."""

from __future__ import annotations

import json as _json

from odoo_cli.cli._click import click


class Output:
    def echo(self, message: str = "") -> None:
        click.echo(message)

    def success(self, message: str) -> None:
        click.secho(message, fg="green")

    def warn(self, message: str) -> None:
        click.secho(f"warning: {message}", fg="yellow", err=True)

    def error(self, message: str) -> None:
        click.secho(f"error: {message}", fg="red", err=True)

    def hint(self, message: str) -> None:
        """A concise next action, shown after errors or completed commands."""
        click.echo(message, err=True)

    def json(self, data: object) -> None:
        click.echo(_json.dumps(data, indent=2))
