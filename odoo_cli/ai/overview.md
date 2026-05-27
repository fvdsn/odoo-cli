# Odoo Development Workspace

This is an Odoo development workspace managed by `odoo-cli`.

## Repository Structure

The workspace may contain the following repositories (not all may be present):

- `odoo/` — Odoo Community (main codebase)
- `enterprise/` — Odoo Enterprise
- `documentation/` — Odoo Documentation
- `themes/` — Odoo Themes (design-themes)
- `addons/` — Extra addon repositories

## Configuration

- `config.toml` — Workspace configuration (version, repos, postgres, modules)
- `odoo/odoo.conf` — Generated Odoo server configuration
- `odoo/.venv/` — Python virtual environment

## Getting Workspace Info

Run `odoo-cli info` to get current workspace details (version, database, port, installed modules).

## CLI Tool

All commands should be run from the workspace root.

| Command | Description |
|---|---|
| `odoo-cli info` | Show current workspace configuration |
| `odoo-cli start` | Start the Odoo server |
| `odoo-cli update [modules]` | Update modules (default: all) |
| `odoo-cli db-reset` | Drop and recreate the database |
| `odoo-cli test [modules]` | Run tests on a dedicated test database |
| `odoo-cli sql "SELECT ..."` | Execute a SQL query |
| `odoo-cli psql` | Open an interactive PostgreSQL shell |
| `odoo-cli shell` | Python REPL with Odoo environment |
| `odoo-cli run "code"` | Execute Python in Odoo environment |
| `odoo-cli checkout [version]` | Switch all repos to a version |
| `odoo-cli pull` | Pull latest changes across all repos |
| `odoo-cli venv` | Recreate the Python virtual environment |

## Python Environment

When running Python directly:
```bash
odoo/.venv/bin/python odoo/odoo-bin [options]
```

## Git Workflow

Feature branches should be pushed to the dev remote (`odoo-dev`), not `origin`.
