import typer

from odoo_cli.commands import ai_setup, checkout, config, db_reset, info, init, pull, rpc, setup_venv, shell, sql, start, test, update

app = typer.Typer(
    name="odoo-cli",
    help="CLI tool for Odoo development workflows.",
    no_args_is_help=True,
)

app.command()(info.info)
app.command()(init.init)
app.command()(config.config)
app.command()(checkout.checkout)
app.command()(pull.pull)
app.command()(setup_venv.venv)
app.command()(start.start)
app.command()(update.update)
app.command("db-reset")(db_reset.db_reset)
app.command()(sql.sql)
app.command()(sql.psql)
app.command()(rpc.rpc)
app.command()(shell.shell)
app.command()(shell.run)
app.command()(test.test)
app.command("ai-setup")(ai_setup.ai_setup)

if __name__ == "__main__":
    app()
