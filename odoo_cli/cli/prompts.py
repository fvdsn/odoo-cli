"""click.prompt/click.confirm wrappers.

Commands prompt only through this module so tests can assert prompting
behavior and core stays free of stdin access.
"""

from __future__ import annotations

from odoo_cli.cli._click import click


def confirm(question: str, *, default: bool = False) -> bool:
    return click.confirm(question, default=default)


def prompt(text: str, *, default: str | None = None, hide_input: bool = False) -> str:
    return click.prompt(text, default=default, hide_input=hide_input)
