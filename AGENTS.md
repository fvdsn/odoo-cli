# Agent Notes

## Purpose

`odoo-cli` is a Python CLI for managing local Odoo development instances. It
keeps one workspace, uses git worktrees for parallel version/customer work,
shares venvs by detected Odoo version, derives database names from worktrees,
and allocates ports automatically.

The guiding rule is that derived state should come from the filesystem, the
database, git, and `odoo/odoo/release.py`. Avoid adding parallel config or
metadata when the same fact can be inferred from those sources.

## Specs And Design

The product requirements, use cases, and architecture live in `specs/`.
Read those files before changing behavior:

- `specs/requirements.md`
- `specs/usecase.md`
- `specs/architecture.md`

Versioned follow-up specs such as `specs/requirements_v2.md`,
`specs/requirements_v3.md`, and `specs/usecase_v2.md` describe later-stage
features. Do not duplicate those specs here.

## Project Shape

- `odoo_cli/cli/`: click frontend and terminal rendering.
- `odoo_cli/commands/`: thin command adapters.
- `odoo_cli/core/`: frontend-independent domain logic.
- `odoo_cli/util/`: small standard-library helpers.
- `tests/`: unit, CLI, integration, and opt-in e2e tests.

Keep `core` free of click imports, printing, stdin reads, and `sys.exit`.
Subprocess work should go through the injectable process runner patterns already
used in `odoo_cli/util/`.

Runtime dependencies are intentionally minimal: Python standard library plus
vendored click. Do not add new runtime dependencies without checking the specs.

## Useful Commands

```bash
python3 -m unittest discover
python3 -m ruff check .
```

Opt-in real-Odoo flows:

```bash
ODOO_CLI_E2E=1 ODOO_CLI_E2E_ODOO_REPO=~/src/odoo \
    python3 -m unittest discover tests/e2e -v
```
