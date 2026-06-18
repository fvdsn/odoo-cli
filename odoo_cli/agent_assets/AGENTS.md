# Odoo development workspace

This directory is an **Odoo development workspace** managed by the `odoo` CLI
(`odoo-cli`). It is **not** a single git repository: each top-level directory is
a **worktree** (an isolated set of checkouts for one Odoo version or feature),
and the git repositories live *inside* those worktrees.

## Layout

- `<worktree>/` — a worktree. Contains `odoo/` (Odoo Community) and, when
  enabled, `enterprise/`, `themes/`, `documentation/`, plus any customer addon
  checkouts. A *linked* worktree shares another worktree's `odoo/` through a
  symlink instead of its own checkout.
- `.repositories/` — bare git repositories that back the worktrees.
- `.venvs/` — Python virtualenvs, one per detected Odoo version.
- `.run/` — runtime state (allocated ports, …), per worktree and database.

Do **not** guess the current version, database, or ports from this file — they
change and are not written here. Run `odoo where` for the resolved workspace,
worktree, database, venv, and port; run `odoo --help` for the commands.

## Operating the workspace

If an `odoo-cli` skill is available, use it for how to run, update, test, and
manage this workspace. Otherwise rely on `odoo where` and `odoo --help`.

Frequently used:

- `odoo start` — start the server in this terminal (Ctrl-C to stop).
- `odoo update [modules]` — update modules in the database (all if omitted).
- `odoo test <modules>` — run tests (`installed` and `all` are accepted).
- `odoo module install <name>` — install a module (creates the db if needed).
- `odoo shell` — Python REPL with the Odoo environment loaded.
- `odoo db reset` — drop and recreate the database, reinstalling its modules.
- `odoo worktree create <name> [source]` — add a worktree.

Commands work from any directory inside a worktree. From the workspace root,
target inference only works when there is a single unambiguous worktree; when in
doubt, run `odoo where` and pass `-w` / `-d` explicitly. Run any command with
`--help` for its options.

You can edit this file freely; `odoo-cli` writes it once and never rewrites it.
