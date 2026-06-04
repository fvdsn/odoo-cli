# Odoo CLI use cases

This document describes concrete user flows for the Odoo CLI. It complements
`requirements.md`: requirements define the rules, while this file shows the
commands, resulting workspace layout, and source of truth for common scenarios.

The examples intentionally avoid duplicated state:

- worktree version is inferred from the checked-out Odoo source
- active custom addons are inferred from the worktree filesystem
- assigned server ports live in `.run/{worktree}/{db}/ports`
- persistent Odoo data lives in `.data/{worktree}/{db}/`
- `workspace.toml` stores configuration, repository URLs, and per-worktree
  overrides, not derived runtime facts

## 1. First local Odoo setup

Goal: a new user installs the CLI, creates a workspace, starts Odoo, and sees a
working CRM database with demo data.

Commands:

```bash
uv tool install odoo-cli
odoo init          # defaults to latest stable version (e.g. 19.0)
odoo start
```

(`odoo init 19.0` also works to pin a specific version.)

Expected workspace setup:

```text
~/odoo/
    workspace.toml
    .repositories/
        odoo.git
        documentation.git
    .venvs/
        19.0/
    .run/
        19.0/
            odoo-19.0/
                pid
                log
                ports
                socket
                args
    .data/
        19.0/
            odoo-19.0/
                filestore/
    19.0/
        odoo/
        documentation/
```

Relevant `workspace.toml` shape:

```toml
[odoo_cli]
schema_version = 1

[odoo]
admin_user = "admin"
admin_password = "admin"
demo_data = true
dev_mode = true
install_modules = ["crm"]

[repositories]
odoo = "git@github.com:odoo/odoo.git"
documentation = "git@github.com:odoo/documentation.git"
enterprise = false
themes = false
upgrade = false
```

Source of truth:

- initial checkout target comes from the `odoo init 19.0` command
- actual Odoo version is inferred from `~/odoo/19.0/odoo/odoo/release.py`
- target worktree resolves to `19.0` because it is the only worktree
- default database is `odoo-19.0`
- assigned ports are in `.run/19.0/odoo-19.0/ports`

## 2. Daily development in one worktree

Goal: a developer returns to an existing worktree, starts the server in the
background, checks status, watches logs, updates modules, and stops the server.

Commands:

```bash
odoo status
odoo start --background
odoo log --follow
odoo update
odoo test installed
odoo stop
```

Expected workspace setup:

```text
~/odoo/
    .run/
        19.0/
            odoo-19.0/
                pid
                log
                ports
                socket
                args
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
- once multiple worktrees exist, the same commands must be run from inside the
  target worktree or with `--worktree`
- target database defaults to `odoo-19.0`
- `odoo status` reads running server details from `.run/19.0/odoo-19.0/`
- restart parameters are read from `.run/19.0/odoo-19.0/args`

## 2b. Edit-reload-update cycle

Goal: a developer edits code and sees the result in the browser. This is the
most common daily loop — XML edits auto-reload, Python edits restart the server,
and model changes require a database update.

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
# Python changes require a server restart
odoo restart
# refresh the browser

# Add a new field or change model schema
$EDITOR 19.0/odoo/addons/sale/models/sale_order.py
# model/schema changes require a module update to apply to the database
odoo update sale
# refresh the browser

```

Source of truth:

- dev mode is enabled by default: XML changes auto-reload, Python changes
  require a manual `odoo restart`
- model/schema changes (new fields, altered constraints) require
  `odoo update <module>` to update the database
- installing new modules is done through the Odoo UI; to persist across
  db resets, add them via `odoo configure -w <worktree>`
- the server does not need to be stopped for `odoo update`

## 3. Multiple Odoo versions with explicit worktree selection

Goal: a developer keeps both the latest stable version and `master` available in
the same workspace, and chooses the target explicitly.

Commands using `-w`:

```bash
# starting from the workspace created by `odoo init 19.0`
odoo worktree create master

odoo start -w 19.0 --background
odoo start -w master --background

odoo status -w 19.0
odoo status -w master

odoo stop -w 19.0
odoo stop -w master
```

Alternative: `cd` into the worktree instead of using `-w`:

```bash
cd ~/odoo/19.0 && odoo start --background
cd ~/odoo/master && odoo start --background
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
                pid
                log
                ports
                socket
                args
        master/
            odoo-master/
                pid
                log
                ports
                socket
                args
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

## 4. Feature development with a full worktree

Goal: a developer creates an isolated source worktree for a POS feature or bug
fix, then changes the configured startup modules from the default CRM app to
Point of Sale.

Commands:

```bash
odoo worktree create fix-pos-flow 19.0
cd ~/odoo/fix-pos-flow
odoo configure -w fix-pos-flow
# choose installed modules: point_of_sale
odoo db reset
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
                pid
                log
                ports
                socket
                args
    .data/
        fix-pos-flow/
            odoo-fix-pos-flow/
                filestore/
    fix-pos-flow/
        odoo/
        documentation/
```

Resulting `workspace.toml` shape:

```toml
[worktrees.fix-pos-flow.odoo]
install_modules = ["point_of_sale"]
```

Source of truth:

- `fix-pos-flow/odoo` and `fix-pos-flow/documentation` are real git worktrees
- the version is inferred from `fix-pos-flow/odoo/odoo/release.py`
- default database is `odoo-fix-pos-flow`
- configured startup modules live in `workspace.toml`; the worktree-specific
  value overrides the workspace default CRM app
- `odoo configure -w fix-pos-flow` is the human path to create that override
- `odoo db reset` recreates the database and installs the resolved configured
  modules
- no `workspace.toml` worktree entry is required for source metadata; the entry
  exists here only because this use case adds a worktree-specific override

## 5. Enabling enterprise for local development

Goal: a developer enables enterprise once, then decides whether existing
worktrees should receive it.

Commands:

```bash
odoo configure
# choose enterprise
# choose whether to add it to all compatible, selected, or no existing worktrees

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

Relevant `workspace.toml` shape:

```toml
[repositories]
odoo = "git@github.com:odoo/odoo.git"
documentation = "git@github.com:odoo/documentation.git"
enterprise = "git@github.com:odoo/enterprise.git"
themes = false
upgrade = false
```

Source of truth:

- repository URL lives in `workspace.toml`
- bare repository lives in `.repositories/enterprise.git`
- enterprise is active for a worktree when `enterprise/` exists in that worktree
- if the enterprise repository lacks a worktree's detected Odoo version, the CLI
  skips that worktree and reports a warning

## 6. Support workflow: many customer databases, standard Odoo source

Goal: support works with several customer databases on the same standard Odoo
version without duplicating the Odoo source tree.

Commands:

```bash
odoo worktree create 19.0

odoo start -d customer-a --background
odoo start -d customer-b --background

odoo status -d customer-a
odoo status -d customer-b
```

Expected workspace setup:

```text
~/odoo/
    .run/
        19.0/
            customer-a/
                pid
                log
                ports
                socket
                args
            customer-b/
                pid
                log
                ports
                socket
                args
    .data/
        19.0/
            customer-a/
                filestore/
            customer-b/
                filestore/
    19.0/
        odoo/
        documentation/
```

Source of truth:

- both server instances use the same `19.0` worktree
- target worktree resolves to `19.0` because it is the only worktree
- database target is explicit through `-d`
- each `(worktree, database)` pair has its own `.run` and `.data` directory
- customer databases receive distinct ports even though they share the worktree
- no per-database entry is required in `workspace.toml`

## 7. Support workflow: customer addons with linked worktree

Goal: support needs a customer-specific addon repository, but should still avoid
duplicating standard Odoo source directories.

Commands:

```bash
odoo worktree create 19.0

odoo repo add customer-a-addons git@github.com:customer/customer-a-addons.git
odoo repo add support-tools git@github.com:odoo/support-tools.git

odoo worktree create customer-a 19.0 \
  --linked-from 19.0 \
  --addon customer-a-addons \
  --addon support-tools

cd ~/odoo/customer-a
odoo start -d customer-a
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
                pid
                log
                ports
                socket
                args
    .data/
        customer-a/
            customer-a/
                filestore/
    19.0/
        odoo/
        documentation/
    customer-a/
        odoo -> ../19.0/odoo
        documentation -> ../19.0/documentation
        enterprise -> ../19.0/enterprise      <- if enterprise is enabled
        customer-a-addons/
        support-tools/
```

Relevant `workspace.toml` shape:

```toml
[repositories]
odoo = "git@github.com:odoo/odoo.git"
documentation = "git@github.com:odoo/documentation.git"
"customer-a-addons" = "git@github.com:customer/customer-a-addons.git"
"support-tools" = "git@github.com:odoo/support-tools.git"

[worktrees."customer-a"]
linked_from = "19.0"
```

Source of truth:

- `linked_from = "19.0"` marks `customer-a` as a linked worktree
- standard repositories are symlinks to the source worktree
- optional standard repositories such as `enterprise` are symlinked when present
- addon repositories are real git worktrees at the linked worktree root
- active custom addons are discovered from `customer-a/`, not stored in TOML
- `--addon` is a creation-time checkout action only

## 8. Agent-friendly local validation

Goal: an agent starts Odoo, finds the URL and credentials, uses documentation,
executes a machine-readable command, and shuts the server down.

Commands:

```bash
odoo start --background
odoo status --json
odoo rpc /res.partner/search_read '{"domain": [], "fields": ["name"], "limit": 5}'
odoo stop
```

Expected workspace setup:

```text
~/odoo/
    workspace.toml
    .run/
        19.0/
            odoo-19.0/
                ports
                args
    19.0/
        odoo/
        documentation/
```

Source of truth:

- documentation is cloned by default for local reference
- URL and assigned ports come from `.run/{worktree}/{db}/ports`
- Odoo login credentials come from resolved workspace/worktree config
- secrets are redacted in general status/info output unless explicitly requested
- command output for agents should support `--json` where useful

## Future use cases to define

These flows are important, but need more design before they become normative:

- dump, restore, and neutralize for support workflows
- adding or removing addon repositories from an existing linked worktree
- Odoo.sh/cloud backend command sequences
- MCP frontend workflows
- upgrade workflows
- module scaffolding
