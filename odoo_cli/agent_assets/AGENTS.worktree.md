# Odoo worktree

You are inside a **worktree** of an Odoo development workspace managed by the
`odoo` CLI (`odoo-cli`). A worktree is one isolated set of checkouts — `odoo/`
(Odoo Community) and, when present, `enterprise/`, `themes/`, `documentation/`,
and customer addons. In a *linked* worktree `odoo/` is a symlink into another
worktree's checkout.

For the full workspace layout and how to operate it, read the workspace
`../AGENTS.md`. For this worktree's resolved version, database, venv, and port,
run `odoo where`; for the available commands, run `odoo --help`.

If an `odoo-cli` skill is available, use it; otherwise rely on `odoo where` and
`odoo --help`.

You can edit this file freely; `odoo-cli` writes it once and never rewrites it.
