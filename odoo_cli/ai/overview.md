# Odoo Development Workspace

This is an Odoo development workspace managed by `odoo`.

## Repository Structure

The workspace may contain the following repositories (not all may be present):

- `odoo/` — Odoo Community (main codebase)
- `enterprise/` — Odoo Enterprise
- `documentation/` — Odoo Documentation
- `themes/` — Odoo Themes (design-themes)
- `addons/` — Extra addon repositories

## Configuration

- `odoo-workspace.toml` — Workspace configuration (version, repos, postgres, modules)
- `odoo/odoo.conf` — Generated Odoo server configuration
- `odoo/.venv/` — Python virtual environment

## Getting Workspace Info

Run `odoo info` to get current workspace details (version, database, port, installed modules).

## CLI Tool

Commands can be run from the workspace root or any nested directory inside the workspace.

| Command | Description |
|---|---|
| `odoo info` | Show current workspace configuration |
| `odoo doctor` | Check the workspace for common setup problems |
| `odoo start` | Start the Odoo server |
| `odoo update [modules]` | Update modules (default: all) |
| `odoo db-reset` | Drop and recreate the database |
| `odoo test <modules>` | Run tests (module name, `installed`, or `all`) |
| `odoo sql "SELECT ..."` | Execute a SQL query |
| `odoo psql` | Open an interactive PostgreSQL shell |
| `odoo shell` | Python REPL with Odoo environment |
| `odoo shell -c "code"` | Execute Python in Odoo environment |
| `odoo rpc '{"model":...}'` | Execute a JSON-RPC call on the server |
| `odoo checkout [version]` | Switch all repos to a version |
| `odoo pull` | Pull latest changes across all repos |
| `odoo venv` | Recreate the Python virtual environment |

## Python Environment

When running Python directly:
```bash
odoo/.venv/bin/python odoo/odoo-bin [options]
```

## Git Workflow

Feature branches should be pushed to the dev remote (`odoo-dev`), not `origin`.
