---
name: odoo-cli
description: >-
  Operate a local Odoo development workspace with the `odoo` CLI (odoo-cli):
  starting the server, installing/updating modules, running tests, resetting
  the database, the Odoo shell, managing repositories and git worktrees. Use
  in any directory that is an odoo-cli workspace or worktree.
---

# Operating an Odoo workspace with `odoo-cli`

`odoo-cli` manages one workspace of git **worktrees** (isolated checkout sets,
one per Odoo version or feature). State is derived from the filesystem, the
database, and git — not from config — so prefer asking the tool over guessing.

Always start by orienting:

- `odoo where` — resolved workspace, worktree, database, venv, port, and the
  command that would run. Add `--json` for machine-readable output.
- `odoo --help`, and `odoo <command> --help` — every command's real options.

The target worktree and database are inferred from the current directory; pass
`-w <worktree>` / `-d <database>` to override. Run commands from the workspace
root or from inside a worktree.

## Running and developing

- `odoo start` — start the server in the foreground (Ctrl-C stops it). Dev mode
  is on by default: XML/asset edits auto-reload; Python edits need a restart.
- `odoo update [modules]` — apply model/schema changes to the database
  (all installed modules if none are named). The server need not be stopped.
- `odoo module install <name> [...]` — install modules (creates the database if
  it does not exist yet).
- `odoo test <modules>` — run tests; `installed` and `all` are accepted.
- `odoo shell [-c CODE]` — Python REPL with the Odoo environment; `-c` runs code
  and prints the result.

## Database

- `odoo db reset` — drop and recreate the database, reinstalling the modules it
  currently has. The database is the source of truth for installed modules, so
  installs survive a reset.

## Repositories and worktrees

- `odoo repo add <name> <url>` — clone an additional addon repository.
- `odoo repo enable <name>` — enable a built-in optional repo (enterprise,
  themes, …).
- `odoo worktree create <name> [source]` — create a worktree. `source` is a
  version/ref (`odoo worktree create fix-pos 19.0`) or an existing worktree to
  duplicate (`odoo worktree create customer-b customer-a`). `--linked` shares
  the source's checkouts through symlinks; `--addon <repo>` checks out an added
  repo (requires `--linked`).

## Configuration

- `odoo config list` — resolved `odoo.conf` and enabled optional repositories.
- `odoo config get <key>` / `odoo config set <key> <value>` — read/edit one key
  of the shared `~/.config/odoo/odoo.conf`.

## Notes

- One workspace, located at `$ODOO_DIR` or `~/odoo`.
- Versions come from each worktree's `odoo/odoo/release.py`; venvs are keyed by
  detected version under `.venvs/`.
- Ports are auto-allocated per (worktree, database) under `.run/`.
- If a command's flags here disagree with `--help`, trust `--help` — it matches
  the installed version.
