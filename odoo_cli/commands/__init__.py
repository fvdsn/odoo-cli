"""Thin command adapters.

Command modules parse CLI arguments and call core services; they never build
odoo-bin argv, touch odoo.conf, inspect .run/, infer addons paths, or call
sys.exit (docs/architecture.md → "CLI command shape").
"""

from __future__ import annotations


def register(group) -> None:
    """Attach all command modules to the root click group."""
    # Command modules are appended here as they are implemented, e.g.:
    #   from odoo_cli.commands import init
    #   group.add_command(init.init)
