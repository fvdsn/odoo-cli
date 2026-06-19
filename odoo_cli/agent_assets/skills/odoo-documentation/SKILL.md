---
name: odoo-documentation
description: >-
  Find Odoo documentation in the local, version-matched checkout inside the
  workspace instead of searching the web. Use whenever you need Odoo developer
  reference, tutorials, app docs, or coding/contributing guidelines — for the
  current worktree's version or a specific Odoo version.
---

# Reading the Odoo documentation locally

The workspace ships the **full Odoo documentation as a local git checkout**, one
per worktree, checked out at the **same version as that worktree**. Prefer it
over web searches: it matches the exact Odoo version you are working on, it is
authoritative, and it works offline. Only fall back to the web if the local
checkout is missing or you need a change newer than the checkout.

## Where it is

- Inside a worktree the docs are at `documentation/content/` (i.e.
  `./documentation/content/` from the worktree root). A linked worktree shares
  the source worktree's checkout, so the path still works.
- Run `odoo where` to get the resolved **workspace root** and the **current
  worktree** and its version when you are unsure of the paths.

## Pick the right version

The docs version follows the worktree, so **read from the worktree whose Odoo
version matches the question**:

- Default to the **current** worktree's `documentation/content/` — it matches the
  code you are working on.
- For a different version, use that version's worktree:
  `<workspace>/<version>/documentation/content/` (e.g. `~/odoo/19.0/documentation/
  content/`). The workspace's top-level directories are worktrees — `ls` the
  workspace root to see which versions exist.
- If no worktree exists for the version you need, the current worktree's docs are
  usually close enough; otherwise create one with `odoo worktree create
  <version>` and read from it.

## Table of contents

Paths are relative to `documentation/content/`. Files are reStructuredText
(`.rst`); a name listed below is the `.rst` file or the directory of that name.

### `developer/` — building Odoo modules (start here for code questions)

- `reference/backend/` — server framework:
  - `orm` — models, fields, recordsets, domains, search/read_group, SQL wrapper
  - `actions` — window/server/client actions, crons
  - `data` — XML data files, external ids, `noupdate`, CSV
  - `http` — controllers and routes (`@route`, auth, CSRF)
  - `module` — the `__manifest__.py` manifest
  - `security` — access rights, record rules, field access, security pitfalls
  - `performance` — profiling, batching, complexity, indexes
  - `reports` — QWeb PDF reports
  - `mixins` — common mixins (mail.thread, etc.)
  - `testing` — Python tests, tags, tours
- `reference/frontend/` — web/JS framework:
  - `javascript_reference`, `owl_components`, `javascript_modules` — OWL & ES modules
  - `services`, `registries`, `hooks`, `patching_code` — framework wiring
  - `qweb` — QWeb templates (`t-out`, directives)
  - `assets`, `error_handling`, `framework_overview`, `odoo_editor`, `mobile`,
    `unit_testing`
- `reference/` (other) — `cli`, `external_api`, `external_rpc_api`,
  `extract_api`, `standard_modules`, `upgrades`, `user_interface`
- `tutorials/` — guided builds: `server_framework_101` (the main backend
  walkthrough), `backend`, `define_module_data`, `restrict_data_access`,
  `mixins`, `pdf_reports`, `unit_tests`, `web`, `discover_js_framework`,
  `master_odoo_web_framework`, `website_theme`, `importable_modules`,
  `setup_guide`
- `howtos/` — focused recipes: `company`, `create_reports`, `translations`,
  `javascript_field`/`javascript_view`/`javascript_client_action`,
  `frontend_owl_components`, `standalone_owl_application`, `scss_tips`,
  `accounting_localization`, `connect_device`, `upgrade_custom_db`,
  `website_themes`

### `contributing/` — conventions

- `development/coding_guidelines` — the canonical coding guidelines (Python, XML,
  JS, SCSS, naming, structure)
- `development/git_guidelines`, `documentation/`, `install_git`

### `applications/` — functional / end-user docs, per app

`essentials`, `finance`, `general`, `hr`, `inventory_and_mrp`, `marketing`,
`productivity`, `sales`, `services`, `studio`, `websites`

### `administration/` — install, deploy, maintain, upgrade

`on_premise`, `odoo_sh`, `odoo_online`, `odoo_accounts`, `upgrade`, `hosting`,
`mobile`, `neutralized_database`

### `legal/`

License and legal notices.

## How to search

Grep/ripgrep across the `.rst` files under the right `content/` subtree, then read
the matching files. Examples (from a worktree root):

```bash
rg -n "read_group" documentation/content/developer/reference
rg -l "record rule" documentation/content/developer/reference/backend
```

Scope the search to `developer/` for framework/API questions, `contributing/` for
conventions, `applications/` for functional behavior, and `administration/` for
deployment.
