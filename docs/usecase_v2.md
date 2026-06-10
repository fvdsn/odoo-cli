# Odoo CLI use cases (v2)

Flows that depend on v2 commands. v1 flows live in `usecase.md`; v1 is scoped to
the foreground dev loop (see `requirements_v2.md` for the full list of deferred
commands). These use background servers, `status`/`log`, `rpc`, and the support /
linked-worktree workflows. With the v2 server lifecycle, `.run/{worktree}/{db}/`
gains the `pid`, `log`, `socket`, and `args` files alongside `ports`.

## 1. Support workflow: many customer databases, standard Odoo source

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
- nothing is stored per database; each database's `.run`/`.data` directories and
  its installed modules are the only state

## 2. Support workflow: customer addons with linked worktree

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

No config file changes — repos and links are all on disk.

Source of truth:

- `odoo repo add` clones each addon repo into `.repositories/*.git`; that presence
  is the registry (URLs are the bare repos' git remotes)
- the symlinked `customer-a/odoo -> ../19.0/odoo` marks `customer-a` as a linked
  worktree and identifies `19.0` as its source (the former `linked_from`)
- standard repositories are symlinks to the source worktree
- optional standard repositories such as `enterprise` are symlinked when present
- addon repositories are real git worktrees at the linked worktree root
- active custom addons are discovered from `customer-a/`, not stored anywhere
- `--addon` is a creation-time checkout action only

## 3. Agent-friendly local validation

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
~/.config/odoo/odoo.conf    <- shared config, outside the workspace
~/odoo/
    .repositories/
        odoo.git
        documentation.git
    .run/
        19.0/
            odoo-19.0/
                pid
                log
                ports
                socket
                args
    19.0/
        odoo/
        documentation/
```

Source of truth:

- documentation is cloned by default for local reference
- URL and assigned ports come from `.run/{worktree}/{db}/ports`
- `odoo rpc` authenticates with the resolved Odoo login credentials (v2 makes
  these configurable; the default remains `admin` / `admin`)
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
