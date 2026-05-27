# odoo-cli

CLI tool for Odoo development workflows. Manages multi-repo workspaces, server lifecycle, database operations, and testing.

## Installation

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv tool install -e .
```

## Setup

```bash
odoo-cli init [directory]
```

Interactive wizard that sets up:
- Repository cloning (odoo, enterprise, documentation, themes, extra addons)
- Git user config and dev remotes
- Python virtual environment
- PostgreSQL connection
- `odoo.conf` generation
- AI context files for coding assistants (Claude, Copilot, Codex, OpenCode, Pi)

Configuration is saved to `config.toml` and reused on subsequent runs.

## Commands

| Command | Description |
|---|---|
| `odoo-cli init [dir]` | Set up a new Odoo workspace |
| `odoo-cli checkout [version]` | Switch all repos to a version branch |
| `odoo-cli pull` | Pull latest changes across all repos |
| `odoo-cli venv` | Set up or recreate the Python virtual environment |
| `odoo-cli start` | Start the Odoo server |
| `odoo-cli update [modules]` | Update modules without restarting (`all` by default) |
| `odoo-cli db-reset` | Drop and recreate the database |
| `odoo-cli test [modules]` | Run tests on a dedicated test database |
| `odoo-cli sql "SELECT ..."` | Execute a SQL query |
| `odoo-cli psql` | Open an interactive PostgreSQL shell |
| `odoo-cli shell` | Python REPL with the Odoo environment loaded |
| `odoo-cli run "code"` | Execute Python code in the Odoo environment |
| `odoo-cli ai-setup` | Regenerate AI context files and skills |

Run `odoo-cli <command> --help` for detailed usage.
