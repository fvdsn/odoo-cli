---
name: odoo-changelog
description: >-
  Breaking and notable Odoo changes across versions 17.0, 18.0, and 19.0 —
  ORM/Python, view/XML syntax, and the JS framework — for Odoo 17.0, 18.0,
  19.0, and 20.0 (master) — baked in so you can tell whether an API or syntax is
  current for the worktree's version without diffing old docs. Use when writing
  or reviewing Odoo code, or when unsure an API, field attribute, view tag, or
  template directive is still current.
---

# Odoo version changes (17.0 → 20.0)

A common failure is writing an Odoo API or syntax that was renamed or removed in
a newer version. This skill bakes in the notable changes so you don't have to
check out old documentation.

The ORM section is distilled from Odoo's authoritative ORM changelog
(`documentation/content/developer/reference/backend/orm/changelog.rst`). The XML
and JS sections list the **major** shifts (Odoo does not keep a single changelog
for those); for exhaustive or version-exact detail, read the worktree's
reference docs via the `odoo-documentation` skill.

## How to use it

1. Find the worktree's Odoo version (`odoo where`, or `odoo/odoo/release.py`).
2. Use the **modern** form at or after the version it landed in; on an older
   worktree, use the old form. Entries are tagged with the version (and the
   `.x` minor where relevant).
3. If something isn't listed, verify against the worktree's `orm/changelog.rst`
   and docs rather than trusting memory.

## 17.0

ORM / Python:

- Build raw SQL with the `odoo.tools.SQL` wrapper (the ORM uses it internally);
  it composes safely against injection.
- Field attribute `group_operator` is renamed to `aggregator` (17.2). You can
  also group/aggregate/order by a related non-stored field (17.2).
- `read_group` (and domains) can group by date-part numbers (17.3).
- The internal `inselect` operator is removed — use `in` with a `Query`/`SQL`
  object (17.4). `Model._flush_search` is deprecated (17.1).

Views / XML:

- `attrs="{...}"` and `states="..."` are **removed**. Put Python expressions
  directly on the node instead: `invisible="state == 'draft'"`, `readonly="..."`,
  `required="..."`, `column_invisible="..."`.

Templates:

- QWeb output uses `t-out` (auto-escaping). `t-esc` and `t-raw` are superseded by
  it.

JS:

- The web framework is OWL-based (components, services, registries, hooks); use
  the `frontend/` reference docs for the current APIs.

## 18.0

ORM / Python:

- Name search is implemented as `_search_display_name` like any other field
  (18.0).
- Access checks are combined: `check_access` / `has_access` (and
  `_filtered_access`) replace the older separate access-right/rule checks (18.0).
- Translations come from the environment — `self.env._("...")` (18.0).
- New `odoo.Domain` API to build and combine domains safely (18.1).
- Declare SQL constraints and indexes as **model attributes** (18.1).
- JSON controllers use `type='jsonrpc'` (renamed from `json`; the call protocol
  is unchanged) (18.1).
- `read_group()` is deprecated → `_read_group()` (backend) and
  `formatted_read_group()` (public, formatted) (18.2).
- `@api.private` marks a public Python method as **not** RPC-callable (18.2).
- Demo data is no longer loaded by default (18.3).

Views / XML:

- The list view tag is `<list>` (renamed from `<tree>`) — use `<list>` on 18.0+,
  `<tree>` only on 17.0.

JS:

- The JavaScript unit-testing framework moved to **Hoot** (replacing QUnit), with
  new test helpers and a mock server — see `frontend/unit_testing/`.

## 19.0

ORM / Python:

- `record._cr` / `record._context` / `record._uid` are deprecated → use
  `self.env.cr` / `self.env.context` / `self.env.uid`.
- `odoo.osv` is deprecated.
- `read_group`/pivot gain `GROUPING SETS`; domains support dynamic dates.

Views / XML & JS:

- Mostly incremental; verify specific view/widget or framework details against
  the worktree's reference docs.

## 20.0 (master)

master is frozen for 20.0. In the ORM changelog these land as "Odoo Online
19.1–19.4"; treat them as the next major's changes and verify against the master
worktree.

ORM / Python:

- **Binary fields** now hold a `BinaryValue` of **raw bytes**, not a base64
  string — stop base64-encoding/decoding Binary field values across the data
  flow (19.2–19.3).
- `ir.access` merges access rights and record rules into one mechanism (19.4); a
  domain `access` operator can check the comodel's permissions explicitly (19.3).
- `Field.compute_sql` lets a computed field produce SQL, so you can group by and
  order by it; plus a new SQL-building API and a new `ir.config_parameter` API
  (19.1).
- Simpler `Model.concat` / `Model.union`; write multiple translations in one
  `write`; x2many field access returns only the records you can access
  (cache-pollution fix) (19.3).
- In model code prefer `env.website` over `request` (19.4).

Views / XML:

- `<list>` and inline view expressions as in 18.0/19.0 — no new view-tag break.

JS — OWL 3:

- 20.0 upgrades the web framework to **OWL 3**, a major version with broad
  breaking changes across reactivity, hooks, component lifecycle, props, and
  templates. **Treat your OWL 2 knowledge as outdated**: don't assume an OWL 2
  API, hook, or template directive still exists or behaves the same. Before
  writing or reviewing OWL components on master, consult the OWL 3 migration
  guide and the master `frontend/` docs, and verify each API there.
- **Bundled migration guide: `owl3-migration.md`** (next to this file) — the full
  OWL 2 → OWL 3 breaking-change list with before/after code (e.g. `useState`/
  `reactive` → `proxy`, `this.props`/`static props` → the `props()` function,
  `this.env`/`useSubEnv` → plugins, `t-ref`/`t-model` take a signal, `t-esc` →
  `t-out`, `useEffect`/`onWillUpdateProps`/`onWillRender`/`onRendered`/`this.render`
  changes). It is a DRAFT copy; the upstream guide and the OWL/Odoo code are the
  final word:
  <https://odoo.github.io/owl/documentation/v3/owl/migration_owl2_to_owl3.html>.

## Still commonly written wrong (pre-17.0, but you will reach for the old form)

- `name_get()` → compute `display_name` via `_compute_display_name` (16.4).
- `search(args=...)` → `search(domain=...)`; `browse()` rejects `str` ids (15.3).
- Translated fields are stored as JSONB; code translations come from PO files,
  not the database (16.0).

## Verify against the worktree

For anything not listed here, or for exact view/widget and JS-framework details,
the worktree's docs are authoritative: read
`documentation/content/developer/reference/backend/orm/changelog.rst` (the
per-version ORM changelog) and the `developer/reference/{backend,frontend,
user_interface}` pages (the `odoo-documentation` skill explains where they are).
