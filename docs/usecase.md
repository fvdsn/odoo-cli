# Odoo CLI use cases (v1)

This document describes concrete user flows for the v1 Odoo CLI. It complements
`requirements.md`: requirements define the rules, while this file shows the
commands, resulting workspace layout, and source of truth for common scenarios.
Flows that depend on v2 commands (background servers, status/log, rpc, support
and linked-worktree workflows) live in `usecase_v2.md`.

The examples intentionally avoid duplicated state:

- worktree version is inferred from the checked-out Odoo source
- active custom addons are inferred from the worktree filesystem
- the repository set is read from `.repositories/` and the worktree layout from disk
- assigned server ports live in `.run/{worktree}/{db}/ports`
- persistent Odoo data lives in `.data/{worktree}/{db}/`
- the only configuration file is the shared `~/.config/odoo/odoo.conf` (Odoo's own
  format); the CLI keeps no `workspace.toml` and stores no derived runtime facts

In v1 the server runs in the foreground (Ctrl-C to stop), so `.run/{worktree}/{db}/`
holds only the `ports` file. The pid/log/socket/args files appear with the v2
server lifecycle.

## 1. First local Odoo setup

Goal: a new user installs the CLI, creates a workspace, installs CRM, and starts
Odoo with demo data.

Commands:

```bash
uv tool install odoo-cli
odoo init                 # defaults to latest stable version (e.g. 19.0); empty db
odoo module install crm   # install CRM (demo data on by default)
odoo start
```

Alternative:
```bash
curl http://odoo.com/get-started.sh (installs odoo-cli, then odoo init)
odoo module install crm
odoo start
```

(`odoo init 19.0` also works to pin a specific version.)

Expected workspace setup:

```text
~/.config/odoo/odoo.conf    <- shared config, outside the workspace
~/odoo/
    .repositories/
        odoo.git
        documentation.git
    .venvs/
        19.0/
    .run/
        19.0/
            odoo-19.0/
                ports
    .data/
        19.0/
            odoo-19.0/
                filestore/
    19.0/
        odoo/
        documentation/
```

`odoo init` writes the shared `~/.config/odoo/odoo.conf` with good defaults:

```ini
[options]
db_host = False
db_port = False
db_user = False
db_password = False
dev_mode = all
without_demo = False
log_level = warn
```

Source of truth:

- initial checkout target comes from the `odoo init 19.0` command
- actual Odoo version is inferred from `~/odoo/19.0/odoo/odoo/release.py`
- enabled repos are exactly those present in `.repositories/` (here: odoo, documentation)
- target worktree resolves to `19.0` because it is the only worktree
- default database is `odoo-19.0`
- the database starts empty; `odoo module install crm` installs CRM
- installed modules are read back from the database, not from config
- assigned ports are in `.run/19.0/odoo-19.0/ports`

## 2. Daily development in one worktree

Goal: a developer returns to an existing worktree, starts the server, updates
modules, and runs tests.

Commands:

```bash
cd ~/odoo/19.0      # target inferred from cwd (or pass -w 19.0)
odoo start          # foreground; Ctrl-C to stop

# --- in another terminal ---
odoo update
odoo test installed
```

Expected workspace setup:

```text
~/odoo/
    .run/
        19.0/
            odoo-19.0/
                ports
    .data/
        19.0/
            odoo-19.0/
                filestore/
    19.0/
        odoo/
        documentation/
```

Source of truth:

- target worktree resolves to `19.0` when it is still the only worktree
- once multiple worktrees exist, run from inside the target worktree or pass `--worktree`
- target database defaults to `odoo-19.0`
- the assigned port is in `.run/19.0/odoo-19.0/ports`
- `odoo update` and `odoo test` do not require stopping the foreground server

## 2b. Edit-reload-update cycle

Goal: a developer edits code and sees the result in the browser. This is the
most common daily loop — XML edits auto-reload, Python edits need a restart, and
model changes require a database update.

Commands:

```bash
cd ~/odoo/19.0
odoo start

# --- in another terminal ---

# Edit an XML view (e.g. change a form layout)
$EDITOR 19.0/odoo/addons/sale/views/sale_order_views.xml
# dev mode auto-reloads XML — just refresh the browser

# Edit a Python file (e.g. a controller or method)
$EDITOR 19.0/odoo/addons/sale/models/sale_order.py
# Python changes need a restart: Ctrl-C the server, then run `odoo start` again
# (v1 has no `odoo restart`)

# Add a new field or change model schema
$EDITOR 19.0/odoo/addons/sale/models/sale_order.py
# model/schema changes require a module update to apply to the database
odoo update sale
# refresh the browser
```

Source of truth:

- dev mode is enabled by default: XML changes auto-reload, Python changes need a
  manual restart (Ctrl-C + `odoo start`; `odoo restart` arrives in v2)
- model/schema changes (new fields, altered constraints) require
  `odoo update <module>` to update the database
- new modules are installed with `odoo module install <module>` (or through the
  Odoo UI); either way they persist across `odoo db reset`, which re-reads the
  installed set from the database
- the server does not need to be stopped for `odoo update`

## 3. Multiple Odoo versions with explicit worktree selection

Goal: a developer keeps both the latest stable version and `master` available in
the same workspace, and chooses the target explicitly.

Commands using `-w`:

```bash
# starting from the workspace created by `odoo init 19.0`
odoo worktree create master

# run each server in its own terminal (foreground)
# terminal 1:
odoo start -w 19.0
# terminal 2:
odoo start -w master
```

Alternative: `cd` into the worktree instead of using `-w`:

```bash
cd ~/odoo/19.0 && odoo start
cd ~/odoo/master && odoo start
```

Expected workspace setup:

```text
~/odoo/
    .repositories/
        odoo.git
        documentation.git
    .venvs/
        19.0/
        master/
    .run/
        19.0/
            odoo-19.0/
                ports
        master/
            odoo-master/
                ports
    .data/
        19.0/
            odoo-19.0/
                filestore/
        master/
            odoo-master/
                filestore/
    19.0/
        odoo/
        documentation/
    master/
        odoo/
        documentation/
```

Source of truth:

- `19.0/odoo` and `master/odoo` are separate git worktrees
- each worktree's Odoo version is inferred from its own `odoo/odoo/release.py`
- because several worktrees exist, commands run outside a worktree must use
  `-w` / `--worktree`
- default databases are derived from the targeted worktree: `odoo-19.0` and
  `odoo-master`
- each `(worktree, database)` pair has its own `.run/` and `.data/` directories
- each server auto-allocates a distinct port, so both can run at once

## 4. Feature development with a full worktree

Goal: a developer creates an isolated source worktree for a POS feature or bug
fix, and installs Point of Sale in that worktree's database.

Commands:

```bash
odoo worktree create fix-pos-flow 19.0
cd ~/odoo/fix-pos-flow
odoo module install point_of_sale
odoo start
odoo test point_of_sale
```

Expected workspace setup:

```text
~/odoo/
    .repositories/
        odoo.git
        documentation.git
    .run/
        fix-pos-flow/
            odoo-fix-pos-flow/
                ports
    .data/
        fix-pos-flow/
            odoo-fix-pos-flow/
                filestore/
    fix-pos-flow/
        odoo/
        documentation/
```

No config file changes — nothing is written for this worktree.

Source of truth:

- `fix-pos-flow/odoo` and `fix-pos-flow/documentation` are real git worktrees
- the version is inferred from `fix-pos-flow/odoo/odoo/release.py`
- default database is `odoo-fix-pos-flow`
- `odoo module install point_of_sale` installs POS into that database
- the database is the source of truth for installed modules; `odoo db reset`
  re-reads the installed set and reinstalls it (so POS survives a reset)
- no config entry exists for the worktree; its existence, version, and installed
  modules are all derived from the filesystem and database

## 5. Enabling enterprise for local development

Goal: a developer enables enterprise once, then decides whether existing
worktrees should receive it.

Commands:

```bash
odoo config enable enterprise
# choose whether to add it to all compatible, selected, or no existing worktrees
# (or: bare `odoo config` walks the same choice interactively)

odoo worktree create enterprise-feature 19.0
cd ~/odoo/enterprise-feature
odoo start
```

Expected workspace setup:

```text
~/odoo/
    .repositories/
        odoo.git
        documentation.git
        enterprise.git
    enterprise-feature/
        odoo/
        documentation/
        enterprise/
```

Source of truth:

- `odoo config enable enterprise` clones the bare repo into `.repositories/enterprise.git`
- enabled-ness is just that presence: the repository URL is its git remote, not a config value
- enterprise is active for a worktree when `enterprise/` exists in that worktree
- new worktrees include enterprise automatically because `enterprise.git` is now present
- if the enterprise repository lacks a worktree's detected Odoo version, the CLI
  skips that worktree and reports a warning
