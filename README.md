# odoo

CLI tool for Odoo development workflows. Manages multi-repo workspaces, server lifecycle, database operations, and testing.

## Installation

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
uv tool install -e .
```

The package exposes `odoo` as the primary executable and `odoo-cli` as a
compatibility alias.

## Setup

```bash
odoo init [directory]
```

Interactive wizard that sets up:
- Repository cloning (odoo, enterprise, documentation, themes, extra addons)
- Git user config and dev remotes
- Python virtual environment
- PostgreSQL connection
- `odoo.conf` generation
- AI context files for coding assistants (Claude, Copilot, Codex, OpenCode, Pi)

Configuration is saved to `odoo-workspace.toml` and reused on subsequent runs.
After initialization, commands can be run from the workspace root or any nested
directory inside the workspace.

## Workspace layout

An initialized workspace is not itself a Git repository. Instead, it contains
one or more Odoo repositories:

```text
workspace/
  odoo-workspace.toml
  odoo/
    odoo.conf
    .venv/
  enterprise/
  documentation/
  themes/
  addons/
```

`odoo-workspace.toml` is the workspace marker. Existing-workspace commands search the
current directory and its parents for the nearest valid `odoo` config, so
commands work from nested paths like `odoo/addons/sale`.

## Typical workflow

```bash
odoo init ~/src/odoo-workspace
cd ~/src/odoo-workspace/odoo/addons/sale
odoo info
odoo doctor
odoo start
odoo update sale
odoo test sale --tags test_sale
```

Use `odoo config` to update workspace settings, then follow the printed
hints when repository selection, version, or AI harness settings changed.

## Commands

| Command | Description |
|---|---|
| `odoo init [dir]` | Set up a new Odoo workspace |
| `odoo doctor` | Check the workspace for common setup problems |
| `odoo checkout [version]` | Switch all repos to a version branch |
| `odoo pull` | Pull latest changes across all repos |
| `odoo venv` | Set up or recreate the Python virtual environment |
| `odoo start` | Start the Odoo server |
| `odoo update [modules]` | Update modules without restarting (`all` by default) |
| `odoo db-reset` | Drop and recreate the database |
| `odoo test <modules>` | Run tests (module name, `installed`, or `all`) |
| `odoo sql "SELECT ..."` | Execute a SQL query |
| `odoo psql` | Open an interactive PostgreSQL shell |
| `odoo shell` | Python REPL with the Odoo environment loaded |
| `odoo shell -c "code"` | Execute Python code in the Odoo environment |
| `odoo rpc '{...}'` | Execute a JSON-RPC call on the Odoo server |
| `odoo ai-setup` | Regenerate AI context files and skills |

Run `odoo <command> --help` for detailed usage.

## Development

```bash
uv run ruff check .
uv run ruff format --check .
uv run python -m unittest discover -s tests
uv run python -m compileall -q odoo_cli tests
uv run --with build python -m build
```

## License

MIT
