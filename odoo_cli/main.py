import typer

from odoo_cli.commands import (
    ai_setup,
    checkout,
    config,
    db_reset,
    info,
    init,
    pull,
    rpc,
    setup_venv,
    shell,
    sql,
    start,
    test,
    update,
)

app = typer.Typer(
    name="odoo",
    help="CLI tool for Odoo development workflows.",
    no_args_is_help=True,
)

COMMANDS = [
    (info.info, None),
    (init.init, None),
    (config.config, None),
    (checkout.checkout, None),
    (pull.pull, None),
    (setup_venv.venv, None),
    (start.start, None),
    (update.update, None),
    (db_reset.db_reset, "db-reset"),
    (sql.sql, None),
    (sql.psql, None),
    (rpc.rpc, None),
    (shell.shell, None),
    (test.test, None),
    (ai_setup.ai_setup, "ai-setup"),
]

for callback, name in COMMANDS:
    app.command(name)(callback)

if __name__ == "__main__":
    app()
