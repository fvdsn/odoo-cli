---
name: odoo
description: Manage Odoo development environment (server, modules, database, tests)
---

Use this skill when the user wants to manage their Odoo development environment:
starting/stopping the server, updating modules, resetting the database, running tests,
executing SQL or Python code, switching versions, or managing repositories.

## Commands

Commands can run from the workspace root or any nested directory inside the workspace.

### Server

- `odoo start` — Start the Odoo server with configured modules and dev mode.
- `odoo update [modules]` — Update modules without restarting. Defaults to all modules. Runs `--stop-after-init`.
- `odoo db-reset` — Drop and recreate the database, reinstall configured modules. Requires interactive confirmation.

### Database

- `odoo sql "query"` — Execute a SQL query on the database. Output goes to stdout.
- `odoo psql` — Open an interactive PostgreSQL shell.

### Python / Odoo Shell

- `odoo shell` — Interactive Python REPL with Odoo environment (`env`, models, cursor).
- `odoo shell -c "code"` — Execute a Python one-liner in Odoo environment. Non-interactive, suitable for automation.

### RPC

- `odoo rpc '{"model": "...", "method": "...", "args": [...], "kwargs": {...}}'` — Execute a JSON-RPC call on the running Odoo server. Uses configured admin credentials. Outputs JSON to stdout.
  - Example: `odoo rpc '{"model": "res.partner", "method": "search_read", "args": [[]], "kwargs": {"fields": ["name"], "limit": 5}}'`

### Testing

- `odoo test [modules]` — Run tests on a dedicated test database. Defaults to configured modules.
  - `--tags/-t "tag"` — Filter by test tags.
  - `--keep-db` — Keep the test database for inspection.
  - `--verbose/-v` — Show full unfiltered output.

### Repository Management

- `odoo checkout [version]` — Switch all repos to a version branch. Validates version exists, checks for uncommitted changes.
  - `--yes/-y` — Skip feature branch confirmation (still fails on dirty repos or unpushed commits).
- `odoo pull` — Pull latest changes (fast-forward only) across all repos.
- `odoo venv` — Recreate the Python virtual environment with correct Python version and dependencies.

### Configuration

Settings are stored in `config.toml` at the workspace root. The `odoo.conf` file is generated at `odoo/odoo.conf`.
