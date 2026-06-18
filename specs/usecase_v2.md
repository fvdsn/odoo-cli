# Odoo CLI use cases (v2)

Flows that depend on v2 commands. v1 flows live in `usecase.md`; v1 is scoped to
the foreground dev loop plus linked worktrees (see `requirements_v2.md` for the
full list of deferred commands). These use background servers, `status`/`log`,
and `rpc`. With the v2 server lifecycle, `.run/{worktree}/{db}/` gains the
`pid`, `log`, `socket`, and `args` files alongside `ports`. The linked-worktree
support flow itself is v1 — see `usecase.md` §6.

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

## 2. Agent-friendly local validation

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
            19.0/
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
- Odoo.sh/cloud backend command sequences (v3, see `requirements_v3.md`)
- MCP frontend workflows (v3, see `requirements_v3.md`)
- upgrade workflows
- module scaffolding
