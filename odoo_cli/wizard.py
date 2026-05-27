"""Interactive workspace configuration wizard."""

import questionary
import typer

from odoo_cli.ai.harnesses import HARNESSES
from odoo_cli.console import console
from odoo_cli.postgres import check_connection
from odoo_cli.repos import DEV_REMOTE_URL, get_available_versions

COMMUNITY_APPS = [
    "account",
    "calendar",
    "contacts",
    "crm",
    "data_recycle",
    "fleet",
    "hr",
    "hr_attendance",
    "hr_expense",
    "hr_holidays",
    "hr_recruitment",
    "hr_skills",
    "im_livechat",
    "lunch",
    "mail",
    "maintenance",
    "marketing_card",
    "mass_mailing",
    "mass_mailing_sms",
    "mrp",
    "point_of_sale",
    "pos_restaurant",
    "project",
    "project_todo",
    "purchase",
    "repair",
    "stock",
    "survey",
    "website",
    "website_event",
    "website_hr_recruitment",
    "website_slides",
]

ENTERPRISE_APPS = [
    "accountant",
    "ai_app",
    "appointment",
    "approvals",
    "databases",
    "delivery_bpost",
    "delivery_dhl_rest",
    "delivery_easypost",
    "delivery_envia",
    "delivery_fedex_rest",
    "delivery_sendcloud",
    "delivery_shiprocket",
    "delivery_starshipit",
    "delivery_ups_rest",
    "delivery_usps_rest",
    "documents",
    "equity",
    "esg",
    "frontdesk",
    "helpdesk",
    "hr_appraisal",
    "hr_payroll",
    "hr_referral",
    "iot",
    "knowledge",
    "marketing_automation",
    "mrp_plm",
    "planning",
    "planning_field_service",
    "quality_control",
    "room",
    "sale_subscription",
    "sign",
    "social",
    "stock_barcode",
    "timesheet_grid",
    "web_studio",
    "whatsapp",
]


def run_wizard(existing: dict | None = None) -> dict:
    """Run the setup wizard. If existing config is provided, use values as defaults."""
    e = existing or {}
    e_user = e.get("user", {})
    e_repos = e.get("repositories", {})
    e_pg = e.get("postgres", {})
    e_odoo = e.get("odoo", {})
    e_ai = e.get("ai", {})

    console.print()
    if existing:
        console.print("[bold]Updating workspace configuration[/bold]\n")
    else:
        console.print("[bold]Welcome to the Odoo workspace setup![/bold]")
        console.print(
            "This wizard will set up the standard Odoo repository structure\n"
            "and configure your development environment.\n"
            "We'll ask you a few questions to get started.\n"
        )

    odoo_employee = questionary.confirm(
        "Are you an Odoo employee?",
        default=e.get("odoo_employee", False),
    ).unsafe_ask()

    full_name = questionary.text(
        "Full name:",
        default=e_user.get("name", ""),
        validate=lambda v: len(v.strip()) > 0 or "Name cannot be empty",
    ).unsafe_ask()

    def validate_email(val):
        val = val.strip()
        if not val:
            return "Email cannot be empty"
        if "@" not in val:
            return "Invalid email address"
        if odoo_employee and not val.endswith("@odoo.com"):
            return "Odoo employees must use an @odoo.com email"
        return True

    email = questionary.text(
        "Email:",
        default=e_user.get("email", ""),
        validate=validate_email,
    ).unsafe_ask()

    versions = get_available_versions()
    default_version = e.get("version", "master")
    version = questionary.select(
        "Odoo version:",
        choices=versions,
        default=default_version if default_version in versions else None,
    ).unsafe_ask()

    enterprise = questionary.confirm(
        "Clone the enterprise repository?",
        default=e_repos.get("enterprise", odoo_employee),
    ).unsafe_ask()

    documentation = questionary.confirm(
        "Clone the documentation repository?",
        default=e_repos.get("documentation", False),
    ).unsafe_ask()

    themes = questionary.confirm(
        "Clone the themes repository?",
        default=e_repos.get("themes", False),
    ).unsafe_ask()

    prev_addons = e_repos.get("extra_addons", [])
    extra_addons: list[str] = list(prev_addons)
    if prev_addons:
        console.print(f"  Current extra addons: {', '.join(prev_addons)}")
    if questionary.confirm(
        "Add extra addons repositories?" if not prev_addons else "Modify extra addons?",
        default=False,
    ).unsafe_ask():
        extra_addons = []
        for url in prev_addons:
            if questionary.confirm(f"  Keep {url}?", default=True).unsafe_ask():
                extra_addons.append(url)
        while True:
            url = (
                questionary.text(
                    "Addons repo git URL (leave empty to stop):",
                )
                .unsafe_ask()
                .strip()
            )
            if not url:
                break
            extra_addons.append(url)

    has_custom_pg = e_pg.get("host") is not False and e_pg.get("host") is not None
    default_postgres = questionary.confirm(
        "Use default PostgreSQL connection? (localhost, default port, current user)",
        default=not has_custom_pg,
    ).unsafe_ask()

    if default_postgres:
        postgres = {
            "host": False,
            "port": False,
            "user": False,
            "password": False,
        }
    else:
        postgres = {
            "host": questionary.text(
                "PostgreSQL host:",
                default=str(e_pg.get("host", "localhost")) if e_pg.get("host") else "localhost",
            ).unsafe_ask(),
            "port": int(
                questionary.text(
                    "PostgreSQL port:",
                    default=str(e_pg.get("port", 5432)) if e_pg.get("port") else "5432",
                    validate=lambda v: v.isdigit() or "Must be a number",
                ).unsafe_ask()
            ),
            "user": questionary.text(
                "PostgreSQL user:",
                default=str(e_pg.get("user", "odoo")) if e_pg.get("user") else "odoo",
            ).unsafe_ask(),
            "password": questionary.text(
                "PostgreSQL password:",
                default=str(e_pg.get("password", "")) if e_pg.get("password") else "",
            ).unsafe_ask(),
        }

    console.print("  Checking PostgreSQL connection...", end=" ")
    ok, err = check_connection(postgres)
    if ok:
        console.print("[green]OK[/green]")
    else:
        console.print("[red]failed[/red]")
        console.print(f"    [dim]{err}[/dim]")
        if not questionary.confirm("Continue anyway?", default=False).unsafe_ask():
            raise typer.Exit(code=1)

    db_name = questionary.text(
        "Default database name:",
        default=e_pg.get("db_name", "odoo-dev"),
    ).unsafe_ask()

    admin_user = questionary.text(
        "Admin username:",
        default=e_odoo.get("admin_user", "admin"),
    ).unsafe_ask()

    admin_password = questionary.text(
        "Admin password:",
        default=e_odoo.get("admin_password", "admin"),
    ).unsafe_ask()

    http_port = int(
        questionary.text(
            "HTTP port:",
            default=str(e_odoo.get("http_port", 8069)),
            validate=lambda v: v.isdigit() or "Must be a number",
        ).unsafe_ask()
    )

    websocket_port = int(
        questionary.text(
            "WebSocket port:",
            default=str(e_odoo.get("websocket_port", 8072)),
            validate=lambda v: v.isdigit() or "Must be a number",
        ).unsafe_ask()
    )

    data_dir = questionary.text(
        "Data directory:",
        default=e_odoo.get("data_dir", "~/.local/share/Odoo"),
    ).unsafe_ask()

    demo_data = questionary.confirm(
        "Load demo data?",
        default=e_odoo.get("demo_data", True),
    ).unsafe_ask()

    prev_dev_mode = e_odoo.get("dev_mode", False)
    dev_mode = questionary.select(
        "Default run mode:",
        choices=["development (hot reload)", "production"],
        default="development (hot reload)" if prev_dev_mode else "production",
    ).unsafe_ask()
    dev_mode = dev_mode.startswith("development")

    apps = COMMUNITY_APPS[:]
    if enterprise:
        apps.extend(ENTERPRISE_APPS)
    apps.sort()

    prev_modules = set(e_odoo.get("install_modules", []))
    install_modules = questionary.checkbox(
        "Modules to install (space to select, enter to confirm):",
        choices=[questionary.Choice(app, checked=app in prev_modules) for app in apps],
    ).unsafe_ask()

    if odoo_employee:
        dev_remote_url = DEV_REMOTE_URL
    else:
        dev_remote = questionary.select(
            "Where do you push feature branches?",
            choices=["your own fork", "custom remote"],
        ).unsafe_ask()

        if dev_remote == "custom remote":
            dev_remote_url = questionary.text(
                "Custom remote URL (use {repo} as placeholder):",
                default=e.get("remotes", {}).get("dev_url", ""),
                validate=lambda v: len(v) > 0 or "URL cannot be empty",
            ).unsafe_ask()
        else:
            github_user = questionary.text(
                "GitHub username:",
                validate=lambda v: len(v) > 0 or "Username cannot be empty",
            ).unsafe_ask()
            dev_remote_url = f"git@github.com:{github_user}/{{repo}}.git"

    prev_harnesses = set(e_ai.get("harnesses", []))
    ai_harnesses = questionary.checkbox(
        "AI harnesses to set up (space to select):",
        choices=[
            questionary.Choice(label, value=key, checked=key in prev_harnesses)
            for key, label in HARNESSES.items()
        ],
    ).unsafe_ask()

    return {
        "version": version,
        "odoo_employee": odoo_employee,
        "user": {
            "name": full_name.strip(),
            "email": email.strip(),
        },
        "repositories": {
            "enterprise": enterprise,
            "documentation": documentation,
            "themes": themes,
            "extra_addons": extra_addons,
        },
        "remotes": {
            "dev_url": dev_remote_url,
        },
        "postgres": {
            **postgres,
            "db_name": db_name,
        },
        "odoo": {
            "admin_user": admin_user,
            "admin_password": admin_password,
            "http_port": http_port,
            "websocket_port": websocket_port,
            "data_dir": data_dir,
            "demo_data": demo_data,
            "dev_mode": dev_mode,
            "install_modules": install_modules,
        },
        "ai": {
            "harnesses": ai_harnesses,
        },
    }
