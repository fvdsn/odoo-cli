# odoo-cli

CLI tool for Odoo development workflows. Manages multi-repo workspaces, server lifecycle, database operations, and testing.

## Installation

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

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
After initialization, commands can be run from the workspace root or any nested
directory inside the workspace.

## Workspace layout

An initialized workspace is not itself a Git repository. Instead, it contains
one or more Odoo repositories:

```text
workspace/
  config.toml
  odoo/
    odoo.conf
    .venv/
  enterprise/
  documentation/
  themes/
  addons/
```

`config.toml` is the workspace marker. Existing-workspace commands search the
current directory and its parents for the nearest valid `odoo-cli` config, so
commands work from nested paths like `odoo/addons/sale`.

## Typical workflow

```bash
odoo-cli init ~/src/odoo-workspace
cd ~/src/odoo-workspace/odoo/addons/sale
odoo-cli info
odoo-cli start
odoo-cli update sale
odoo-cli test sale --tags test_sale
```

Use `odoo-cli config` to update workspace settings, then follow the printed
hints when repository selection, version, or AI harness settings changed.

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
| `odoo-cli rpc '{...}'` | Execute a JSON-RPC call on the Odoo server |
| `odoo-cli ai-setup` | Regenerate AI context files and skills |

Run `odoo-cli <command> --help` for detailed usage.

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
