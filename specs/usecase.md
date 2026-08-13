# Odoo CLI use cases (v1)

This document describes concrete user flows for the v1 Odoo CLI. It complements
`requirements.md`: requirements define the rules, while this file shows the
commands, resulting workspace layout, and source of truth for common scenarios.
Flows that depend on v2 commands (background servers, status/log, rpc,
dump/restore support workflows) live in `usecase_v2.md`.

The examples intentionally avoid duplicated state:

- worktree version is inferred from the checked-out Odoo source
- active custom addons are inferred from the worktree filesystem
- the repository set is read from `.repositories/` and the worktree layout from disk
- assigned server ports live in `.run/{worktree}/{db}/ports`
- the only configuration file is the shared `~/.config/odoo/odoo.conf` (Odoo's own
  format); the CLI keeps no `workspace.toml` and stores no derived runtime facts

In v1 the server runs in the foreground (Ctrl-C to stop), so `.run/{worktree}/{db}/`
holds only the `ports` file. The pid/log/socket/args files appear with the v2
server lifecycle. v1 also leaves persistent data in odoo-bin's default location
(shared by all dbs/servers); the per-instance `.data/{worktree}/{db}/` arrives in v2.

## 1. First local Odoo setup

Goal: a new user installs the CLI, creates a workspace, installs CRM, and starts
Odoo with demo data.

Commands:

```bash
uv tool install odoo-cli-official
odoo init                 # defaults to latest stable version (e.g. 19.0); empty db
odoo module install crm   # install CRM (demo data on by default)
odoo start
```

Alternative:
```bash
curl https://www.odoo.com/install.sh | bash   # installs odoo-cli, then odoo init
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
            19.0/
                ports
    19.0/
        odoo/
        documentation/
```

(Persistent data is in odoo-bin's default `data_dir`, not under `~/odoo` in v1.)

`odoo init` writes the shared `~/.config/odoo/odoo.conf` with good defaults:

```ini
[options]
dev_mode = all
without_demo = False
log_level = warn
```

(The postgres connection keys — `db_host`, `db_port`, `db_user`,
`db_password` — are not written: absent means "local defaults", and odoo-bin
warns about non-boolean options holding the literal `False`. `odoo config set
db_host …` adds them when needed.)

Source of truth:

- initial checkout target comes from the `odoo init 19.0` command
- actual Odoo version is inferred from `~/odoo/19.0/odoo/odoo/release.py`
- enabled repos are exactly those present in `.repositories/` (here: odoo, documentation)
- target worktree resolves to `19.0` because it is the only worktree
- default database is `19.0`
- the database starts empty; `odoo module install crm` installs CRM
- installed modules are read back from the database, not from config
- assigned ports are in `.run/19.0/19.0/ports`

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
            19.0/
                ports
    19.0/
        odoo/
        documentation/
```

Source of truth:

- target worktree resolves to `19.0` when it is still the only worktree
- once multiple worktrees exist, run from inside the target worktree or pass `--worktree`
- target database defaults to `19.0`
- the assigned port is in `.run/19.0/19.0/ports`
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
        saas-19.4/          <- master's detected version (from release.py)
    .run/
        19.0/
            19.0/
                ports
        master/
            master/
                ports
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
- the `master` worktree's venv is keyed by the version its `release.py` reports
  (e.g. `saas-19.4`), not by the worktree name; it changes as master rolls forward
- because several worktrees exist, commands run outside a worktree must name
  their target: `-w` / `--worktree`, or an unambiguous `-d` (`odoo start -d
  19.0` targets worktree `19.0` since the default database of a worktree is
  its own name; `odoo start -d customer-a` targets the only worktree that
  database has run under)
- default databases are derived from the targeted worktree: `19.0` and
  `master`
- each `(worktree, database)` pair has its own `.run/` directory (just `ports` in v1)
- each server auto-allocates a distinct port, so both can run at once
- in v1 both share odoo-bin's default data location; per-instance `.data/` is v2

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
            fix-pos-flow/
                ports
    fix-pos-flow/
        odoo/
        documentation/
```

No config file changes — nothing is written for this worktree.

Source of truth:

- `fix-pos-flow/odoo` and `fix-pos-flow/documentation` are real git worktrees
- the version is inferred from `fix-pos-flow/odoo/odoo/release.py`
- default database is `fix-pos-flow`
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
odoo repo enable enterprise
# by default adds enterprise to all compatible existing worktrees;
# scope with flags (selected worktrees / future-only) — no prompts in v1

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

- `odoo repo enable enterprise` clones the bare repo into `.repositories/enterprise.git`
- enabled-ness is just that presence: the repository URL is its git remote, not a config value
- enterprise is active for a worktree when `enterprise/` exists in that worktree
- new worktrees include enterprise automatically because `enterprise.git` is now present
- if the enterprise repository lacks a worktree's detected Odoo version, the CLI
  skips that worktree and reports a warning

## 6. Customer addons with a linked worktree

Goal: support needs a customer-specific addon repository on a standard Odoo
version without duplicating the Odoo source tree.

Commands:

```bash
odoo repo add customer-a-addons git@github.com:customer/customer-a-addons.git
odoo repo add support-tools git@github.com:odoo/support-tools.git

odoo worktree create customer-a 19.0 --linked \
  --addon customer-a-addons \
  --addon support-tools

cd ~/odoo/customer-a
odoo start                     # db defaults to customer-a; Ctrl-C to stop
```

Expected workspace setup:

```text
~/odoo/
    .repositories/
        odoo.git
        documentation.git
        customer-a-addons.git
        support-tools.git
    .run/
        customer-a/
            customer-a/
                ports
    19.0/
        odoo/
        documentation/
    customer-a/
        odoo -> ../19.0/odoo
        documentation -> ../19.0/documentation
        customer-a-addons/
        support-tools/
```

No config file changes — repos and links are all on disk.

Source of truth:

- `odoo repo add` clones each addon repo into `.repositories/*.git`; that
  presence is the registry (URLs are the bare repos' git remotes)
- the symlinked `customer-a/odoo -> ../19.0/odoo` marks `customer-a` as a linked
  worktree and identifies `19.0` as its source
- addon repositories are real git worktrees at the linked worktree root; active
  custom addons are discovered from `customer-a/`, not stored anywhere
- `--addon` is a creation-time checkout action only
- commands run from inside `customer-a/` target the linked worktree even though
  the symlinked paths physically point into `19.0/` (logical `$PWD` resolution)

## 6b. Duplicating a worktree

Goal: a developer wants another worktree shaped like an existing one — a second
customer on the same setup, or a parallel branch of a feature worktree.

Commands:

```bash
odoo worktree create customer-b customer-a   # SOURCE is a worktree: duplicate it
odoo worktree create hotfix fix-pos          # fork a full worktree's branches
```

Source of truth:

- a SOURCE that names an existing worktree duplicates it; otherwise SOURCE is
  a version/ref as usual (the readings coincide for version-named worktrees)
- every repo the source has — addons included — is checked out on a branch
  named after the new worktree, starting from the source repo's current branch
- duplication preserves the worktree's nature: `customer-b` comes out linked
  to `19.0` (the same original as `customer-a`, never a symlink chain) with
  its own checkout of `customer-a-addons`; `hotfix` comes out as a full
  worktree with branches forked from `fix-pos`
- uncommitted changes in the source are not copied; branches fork from the
  source's committed HEAD
- the new worktree's database is created from the source's as a template
  (`createdb -T`, filestore included) when it exists and is initialized, so a
  large installed-module set needs no reinstall; `--empty-db` opts out, and
  without a usable source database (or reachable postgres) the database is
  simply created empty on first start, as before
