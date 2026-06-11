"""Thin command adapters.

Command modules parse CLI arguments and call core services; they never build
odoo-bin argv, touch odoo.conf, inspect .run/, infer addons paths, or call
sys.exit (docs/architecture.md → "CLI command shape").
"""

from __future__ import annotations


def register(group) -> None:
    """Attach all command modules to the root click group."""
    from odoo_cli.commands import (
        config,
        db,
        init,
        module,
        shell,
        start,
        test,
        update,
        where,
    )

    group.add_command(config.config)
    group.add_command(db.db)
    group.add_command(init.init)
    group.add_command(module.module)
    group.add_command(shell.shell)
    group.add_command(start.start)
    group.add_command(test.test)
    group.add_command(update.update)
    group.add_command(where.where)
