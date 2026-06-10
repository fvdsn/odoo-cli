# Odoo CLI requirements — v2

This document tracks requirements deferred out of v1. `requirements.md` is the
canonical v1 spec; items here are explicitly out of scope for the first version
and will be designed/promoted later.

## Configurable Odoo application credentials
 - v1 does not manage Odoo login credentials; `odoo rpc` assumes the development
   default `admin` / `admin` (see `requirements.md` → "Odoo application credentials")
 - v2 makes the Odoo login configurable, separate from the PostgreSQL credentials
 - likely stored in `odoo.conf` (decide on concrete keys; note `admin_passwd` in
   `odoo.conf` is the database-management master password, NOT the admin user login)
 - worktree/database-specific overrides to be considered
 - commands that need Odoo authentication use the resolved credentials
 - informational commands may show the configured login but never print the
   password unless explicitly requested

## Deferred from v1 (internal-testing scope reduction)
v1 was scoped to 12 commands for internal testing (init, config, repo —
add/enable, worktree create — full and linked, venv, start, where, module
install, update, test, db reset, shell). The following were specced as v1 but pushed to v2; they
keep a `[v2]` tag inline in `requirements.md`:

 - **Server lifecycle** — `odoo stop`, `odoo restart`, and `odoo start --background`.
   v1 is foreground-only: `odoo start` runs in the terminal, Ctrl-C to stop, and
   `.run/{worktree}/{db}/` holds only the `ports` file. v2 adds background mode,
   the pid/socket/args/log files under `.run/`, and restart from sanitized args.
 - **Per-instance persistent data** — isolating each `(worktree, db)`'s data under
   `.data/{worktree}/{db}/` and passing it as `--data-dir`. v1 uses odoo-bin's
   default data location, shared by all dbs/servers (filestore is still namespaced
   per database name, but sessions and the rest of the data_dir are shared). v2
   also decides whether `db reset` clears that database's filestore.
 - **`odoo config` wizard** — the bare interactive `odoo config` (postgres
   connection, enterprise, dev mode, ...). v1 keeps only `get`/`set`/`list`.
   For enterprise the wizard delegates to `odoo repo enable`.
 - **`odoo venv --apt` / no-venv mode** — running Odoo against system-wide
   python packages installed with apt, possibly without any venv at all
   (v1 always creates a venv, with uv or `python3 -m venv` + pip).
 - **`odoo info`** and **`odoo status`** — overview / status views (`odoo where`,
   the resolved-context view, stayed in v1).
 - **`odoo log`** — log viewer with `--follow`/`--date`/`--search` (needs the v2
   `.run/.../log` file; v1 logs to the terminal).
 - **`odoo rpc`** — path-based RPC for agents.
 - **`odoo db shell`** and **`odoo db query`** — thin wrappers over `psql`.
 - **`odoo worktree list`** and **`odoo worktree remove`**.
 - **`odoo doctor`** — setup diagnostics.
 - **`odoo pull` / `odoo fetch`** — repository sync.

## Already-identified v2 scope (support workflows)
These carry a `[v2]` tag in `requirements.md` and will be fleshed out here:
 - `odoo dump` / `restore` / `neutralize` — database lifecycle for support
 - `odoo checkout` — branch/version switching in a worktree-first model
 - `odoo scaffold` — module skeleton generation

(Linked worktrees and `odoo repo add` were promoted to v1 so support users can
validate them early.)

## Parked ideas
 - offload `odoo.conf` resolution to odoo-bin itself (an odoo-bin command that
   prints the resolved config path/contents), instead of the CLI always passing
   `-c ~/.config/odoo/odoo.conf`; revisit if/when odoo-bin grows such a command
   — part of the broader convention-migration direction, see `requirements_v3.md`
   → "Convention migration into odoo-bin"
