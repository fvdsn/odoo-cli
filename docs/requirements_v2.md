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

## Already-identified v2 scope (defined inline in requirements.md for now)
These carry a `[v2]` tag in `requirements.md` and will migrate here as they are
fleshed out:
 - linked worktrees (`odoo worktree create --linked-from`)
 - `odoo repo add` — register/clone additional addon repositories
 - `odoo dump` / `restore` / `neutralize` — database lifecycle for support
