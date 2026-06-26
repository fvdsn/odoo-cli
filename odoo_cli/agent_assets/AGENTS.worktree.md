# Odoo worktree

You are inside a **worktree** of an Odoo development workspace managed by the
`odoo` CLI (`odoo-cli`). A worktree is one isolated set of checkouts — `odoo/`
(Odoo Community) and, when present, `enterprise/`, `themes/`, `documentation/`,
and customer addons. In a *linked* worktree `odoo/` is a symlink into another
worktree's checkout.

For the full workspace layout and how to operate it, read the workspace
`../AGENTS.md`. For this worktree's resolved version, database, venv, and port,
run `odoo where`; for the available commands, run `odoo --help`.

The `odoo-cli` skills (operating the workspace, code review, security review)
are installed at the **workspace root**, not here. A harness started in this
worktree root will **not** auto-load them — skill discovery stops at the git
repo root, and a worktree root is not one. To use them, either start the harness
at the workspace root, or read the skill directly at
`../.agents/skills/odoo-cli/SKILL.md`. Otherwise rely on `odoo where` and
`odoo --help`.

You can edit this file freely; `odoo-cli` writes it once and never rewrites it.
