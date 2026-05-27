import subprocess
from pathlib import Path

import questionary
import typer
from rich.console import Console

from odoo_cli.config import load_config, save_config
from odoo_cli.postgres import check_connection
COMMUNITY_APPS = [
    "account", "calendar", "contacts", "crm", "data_recycle", "fleet",
    "hr", "hr_attendance", "hr_expense", "hr_holidays", "hr_recruitment",
    "hr_skills", "im_livechat", "lunch", "mail", "maintenance",
    "marketing_card", "mass_mailing", "mass_mailing_sms", "mrp",
    "point_of_sale", "pos_restaurant", "project", "project_todo",
    "purchase", "repair", "stock", "survey", "website", "website_event",
    "website_hr_recruitment", "website_slides",
]

ENTERPRISE_APPS = [
    "accountant", "ai_app", "appointment", "approvals", "databases",
    "delivery_bpost", "delivery_dhl_rest", "delivery_easypost",
    "delivery_envia", "delivery_fedex_rest", "delivery_sendcloud",
    "delivery_shiprocket", "delivery_starshipit", "delivery_ups_rest",
    "delivery_usps_rest", "documents", "equity", "esg", "frontdesk",
    "helpdesk", "hr_appraisal", "hr_payroll", "hr_referral", "iot",
    "knowledge", "marketing_automation", "mrp_plm", "planning",
    "planning_field_service", "quality_control", "room",
    "sale_subscription", "sign", "social", "stock_barcode",
    "timesheet_grid", "web_studio", "whatsapp",
]

from odoo_cli.repos import (
    DEV_REMOTE_URL,
    console,
    get_available_versions,
    get_repos,
    resolve_branch,
    setup_venv,
)


def run_wizard() -> dict:
    console.print()
    console.print("[bold]Welcome to the Odoo workspace setup![/bold]")
    console.print(
        "This wizard will set up the standard Odoo repository structure\n"
        "and configure your development environment.\n"
        "We'll ask you a few questions to get started.\n"
    )

    odoo_employee = questionary.confirm(
        "Are you an Odoo employee?",
        default=False,
    ).unsafe_ask()

    full_name = questionary.text(
        "Full name:",
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
        validate=validate_email,
    ).unsafe_ask()

    versions = get_available_versions()
    version = questionary.select(
        "Odoo version:",
        choices=versions,
    ).unsafe_ask()

    enterprise = questionary.confirm(
        "Clone the enterprise repository?",
        default=odoo_employee,
    ).unsafe_ask()

    documentation = questionary.confirm(
        "Clone the documentation repository?",
        default=False,
    ).unsafe_ask()

    themes = questionary.confirm(
        "Clone the themes repository?",
        default=False,
    ).unsafe_ask()

    extra_addons: list[str] = []
    if questionary.confirm(
        "Add extra addons repositories?",
        default=False,
    ).unsafe_ask():
        while True:
            url = questionary.text(
                "Addons repo git URL (leave empty to stop):",
            ).unsafe_ask().strip()
            if not url:
                break
            extra_addons.append(url)

    default_postgres = questionary.confirm(
        "Use default PostgreSQL connection? (localhost, default port, current user)",
        default=True,
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
            "host": questionary.text("PostgreSQL host:", default="localhost").unsafe_ask(),
            "port": int(questionary.text(
                "PostgreSQL port:",
                default="5432",
                validate=lambda v: v.isdigit() or "Must be a number",
            ).unsafe_ask()),
            "user": questionary.text("PostgreSQL user:", default="odoo").unsafe_ask(),
            "password": questionary.text("PostgreSQL password:").unsafe_ask(),
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
        default="odoo-dev",
    ).unsafe_ask()

    http_port = int(questionary.text(
        "HTTP port:",
        default="8069",
        validate=lambda v: v.isdigit() or "Must be a number",
    ).unsafe_ask())

    websocket_port = int(questionary.text(
        "WebSocket port:",
        default="8072",
        validate=lambda v: v.isdigit() or "Must be a number",
    ).unsafe_ask())

    data_dir = questionary.text(
        "Data directory:",
        default="~/.local/share/Odoo",
    ).unsafe_ask()

    demo_data = questionary.confirm(
        "Load demo data?",
        default=True,
    ).unsafe_ask()

    dev_mode = questionary.select(
        "Default run mode:",
        choices=["development (hot reload)", "production"],
    ).unsafe_ask()
    dev_mode = dev_mode.startswith("development")

    apps = COMMUNITY_APPS[:]
    if enterprise:
        apps.extend(ENTERPRISE_APPS)
    apps.sort()

    install_modules = questionary.checkbox(
        "Modules to install (space to select, enter to confirm):",
        choices=apps,
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
                validate=lambda v: len(v) > 0 or "URL cannot be empty",
            ).unsafe_ask()
        else:
            github_user = questionary.text(
                "GitHub username:",
                validate=lambda v: len(v) > 0 or "Username cannot be empty",
            ).unsafe_ask()
            dev_remote_url = f"git@github.com:{github_user}/{{repo}}.git"

    from odoo_cli.ai.harnesses import HARNESSES
    ai_harnesses = questionary.checkbox(
        "AI harnesses to set up (space to select):",
        choices=[questionary.Choice(label, value=key) for key, label in HARNESSES.items()],
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


def configure_git_user(repo_dir: Path, name: str, email: str) -> None:
    for key, value in [("user.name", name), ("user.email", email)]:
        subprocess.run(
            ["git", "-C", str(repo_dir), "config", key, value],
            check=True,
        )


def clone_repo(name: str, url: str, dest: Path, branch: str, user_name: str, user_email: str) -> bool:
    if dest.exists():
        console.print(f"  [yellow]{name}/[/yellow] already exists, skipping.")
        configure_git_user(dest, user_name, user_email)
        return True

    actual_branch = resolve_branch(url, branch)
    if actual_branch is None:
        console.print(f"  [red]{name}: no valid branch for '{branch}', skipping.[/red]")
        return False
    if actual_branch != branch:
        console.print(
            f"  [yellow]{name}: branch '{branch}' not found, "
            f"falling back to '{actual_branch}'[/yellow]"
        )

    console.print(f"  Cloning [bold]{name}[/bold] ([dim]{actual_branch}[/dim])...")
    try:
        subprocess.run(
            [
                "git", "clone",
                "--branch", actual_branch,
                "-c", f"user.name={user_name}",
                "-c", f"user.email={user_email}",
                url, str(dest),
            ],
            check=True,
        )
        return True
    except subprocess.CalledProcessError:
        console.print(f"  [red]Failed to clone {name}.[/red]")
        return False


def add_dev_remote(repo_dir: Path, repo_name: str, dev_url_template: str) -> None:
    url = dev_url_template.format(repo=repo_name)
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "remote"],
        capture_output=True,
        text=True,
    )
    if "odoo-dev" in result.stdout.splitlines():
        return
    subprocess.run(
        ["git", "-C", str(repo_dir), "remote", "add", "odoo-dev", url],
        check=True,
    )


def generate_odoo_conf(directory: Path, config: dict) -> None:
    from odoo_cli.repos import repo_name_from_url

    conf_path = directory / "odoo" / "odoo.conf"
    pg = config["postgres"]

    addons_paths = [str(directory / "odoo" / "addons")]
    if config["repositories"]["enterprise"]:
        addons_paths.append(str(directory / "enterprise"))
    if config["repositories"]["themes"]:
        addons_paths.append(str(directory / "themes"))
    extra_addons = config["repositories"].get("extra_addons", [])
    addons_dir = directory / "addons"
    for url in extra_addons:
        addons_paths.append(str(addons_dir / repo_name_from_url(url)))

    lines = [
        "[options]",
        f"addons_path = {','.join(addons_paths)}",
    ]

    for key, val in [("db_host", pg["host"]), ("db_port", pg["port"]),
                     ("db_user", pg["user"]), ("db_password", pg["password"])]:
        if val is not False:
            lines.append(f"{key} = {val}")

    lines.extend([
        f"db_name = {pg['db_name']}",
        f"http_port = {config['odoo']['http_port']}",
        f"longpolling_port = {config['odoo']['websocket_port']}",
        f"data_dir = {config['odoo']['data_dir']}",
        "",
    ])

    conf_path.write_text("\n".join(lines))
    console.print(f"\n[bold]Generated[/bold] {conf_path}")


def apply_config(directory: Path, config: dict) -> None:
    repos = get_repos(directory, config)

    addons_dir = directory / "addons"
    extra_addons = config["repositories"].get("extra_addons", [])
    if extra_addons and not addons_dir.exists():
        addons_dir.mkdir()

    version = config["version"]
    user_name = config["user"]["name"]
    user_email = config["user"]["email"]

    console.print("\n[bold]Cloning repositories...[/bold]")
    for name, url, dest in repos:
        ok = clone_repo(name, url, dest, version, user_name, user_email)
        if not ok:
            raise typer.Exit(code=1)

    dev_url = config["remotes"]["dev_url"]
    console.print("\n[bold]Setting up dev remote...[/bold]")
    for name, _url, dest in repos:
        if dest.exists():
            add_dev_remote(dest, name, dev_url)
            console.print(f"  [dim]{name}[/dim] → odoo-dev remote configured")

    console.print("\n[bold]Setting up Python environment...[/bold]")
    if not setup_venv(directory):
        raise typer.Exit(code=1)

    generate_odoo_conf(directory, config)

    # AI context setup
    if config.get("ai", {}).get("harnesses"):
        from odoo_cli.ai.harnesses import SETUP_FUNCTIONS, HARNESSES
        console.print("\n[bold]Setting up AI context files...[/bold]")
        for harness in config["ai"]["harnesses"]:
            setup_fn = SETUP_FUNCTIONS.get(harness)
            if setup_fn:
                files = setup_fn(directory, config)
                console.print(f"  [green]{HARNESSES[harness]}[/green]: {', '.join(files)}")

    console.print("\n[green]Workspace initialized successfully.[/green]")


def init(
    directory: Path = typer.Argument(
        ".",
        help="Directory to initialize the Odoo workspace in.",
    ),
) -> None:
    """Initialize an Odoo development workspace."""
    directory = directory.resolve()

    if not directory.exists():
        directory.mkdir(parents=True)
        console.print(f"Created directory [bold]{directory}[/bold]")

    config = load_config(directory)
    if config:
        console.print(f"Found [bold]config.toml[/bold] in {directory}, skipping wizard.")
    else:
        config = run_wizard()
        save_config(directory, config)
        console.print(f"\nSaved configuration to [bold]{directory}/config.toml[/bold]")

    apply_config(directory, config)
