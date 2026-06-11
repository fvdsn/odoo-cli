# odoo-cli

A CLI tool to manage and develop local Odoo instances: one workspace, git
worktrees for multitasking across versions, shared venvs, derived database
names, and automatic port allocation — with the filesystem, the database, and
`odoo/odoo/release.py` as the only sources of truth. The full design lives in
[`docs/`](docs/) (`requirements.md`, `architecture.md`, `usecase.md`).

## Install

```bash
uv tool install odoo-cli-official   # installs the `odoo` executable
```

Runtime is the Python standard library plus a vendored
[click](https://click.palletsprojects.com) (Python 3.11+); nothing else.

## Quick start

```bash
odoo init                 # workspace at ~/odoo, latest stable, empty db
odoo module install crm
odoo start                # foreground; Ctrl-C to stop
```

The workspace looks like:

```text
~/.config/odoo/odoo.conf  <- the only config file (Odoo's own format/location)
~/odoo/
    .repositories/        <- shared bare clones (presence = enabled)
    .venvs/19.0/          <- one venv per detected Odoo version
    .run/19.0/19.0/ports  <- allocated ports per (worktree, database)
    19.0/                 <- a worktree: odoo/, documentation/, ...
```

## Daily commands

| Command | Description |
|---|---|
| `odoo start [-d DB] [--new-port] [--prod]` | Start the server (foreground) |
| `odoo where [--json]` | Show the resolved context + exact odoo-bin command |
| `odoo update [modules]` | Update modules (default: all installed) |
| `odoo module install <modules>` | Install modules (creates the db if needed) |
| `odoo test <module\|installed\|all> [-t tag]` | Run tests in `{db}-test` |
| `odoo shell [-c CODE]` | Odoo Python REPL / one-shot execution |
| `odoo db reset` | Drop + recreate, reinstalling the db's module set |
| `odoo config get/set/list` | Edit the shared odoo.conf |
| `odoo repo enable <enterprise\|themes\|upgrade>` | Enable an optional repo |
| `odoo repo add <name> <url>` | Clone a custom addon repository |
| `odoo worktree create <name> [version] [--linked-from SRC --addon REPO]` | New worktree |
| `odoo venv` | Rebuild the venv for the current worktree |

Commands infer their target from the current directory (or `-w`/`-d`); the
database defaults to the worktree name.

## Development

```bash
python -m unittest discover            # unit + cli + integration (fast, no network)
ODOO_CLI_E2E=1 ODOO_CLI_E2E_ODOO_REPO=~/src/odoo \
    python -m unittest discover tests/e2e -v   # real-Odoo flows (slow, opt-in)
```

Architecture, layering rules, and the testing strategy are documented in
[`docs/architecture.md`](docs/architecture.md).
