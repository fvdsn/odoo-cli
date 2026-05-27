"""Generate Odoo server configuration files."""

from pathlib import Path

from odoo_cli.console import console
from odoo_cli.odoo import configured_addons_paths


def generate_odoo_conf(directory: Path, config: dict) -> None:
    conf_path = directory / "odoo" / "odoo.conf"
    pg = config["postgres"]

    addons_paths = [
        str(path) for path in configured_addons_paths(directory, config, only_existing=False)
    ]

    lines = [
        "[options]",
        f"addons_path = {','.join(addons_paths)}",
    ]

    for key, val in [
        ("db_host", pg["host"]),
        ("db_port", pg["port"]),
        ("db_user", pg["user"]),
        ("db_password", pg["password"]),
    ]:
        if val is not False:
            lines.append(f"{key} = {val}")

    lines.extend(
        [
            f"db_name = {pg['db_name']}",
            f"http_port = {config['odoo']['http_port']}",
            f"gevent_port = {config['odoo']['websocket_port']}",
            f"data_dir = {config['odoo']['data_dir']}",
            "",
        ]
    )

    conf_path.write_text("\n".join(lines))
    console.print(f"\n[bold]Generated[/bold] {conf_path}")
