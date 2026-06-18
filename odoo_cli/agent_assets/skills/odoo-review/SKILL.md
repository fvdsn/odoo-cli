---
name: odoo-review
description: >-
  Review Odoo module code against the framework's coding guidelines and
  pitfalls: module structure and file naming, Python/ORM idioms, field and
  method conventions, XML views, CSV access rights, JavaScript/QWeb assets,
  SCSS, and performance. Use when reviewing or writing code in an Odoo addon.
---

# Reviewing Odoo code

Review against Odoo's framework conventions, not generic Python style alone.
The directives below come from Odoo's coding guidelines, security, and
performance references. Flag issues with file/line and a concrete fix; do not
auto-fix anything ambiguous.

## Review process

- Read the module's `__manifest__.py` first to understand scope and `depends`.
- Check that the change loads and applies: `odoo update <module>` and
  `odoo test <module>`.
- **Stable vs master.** In a *stable* version, the existing file style
  supersedes these guidelines — never restyle existing code; keep the diff
  minimal. In *master*, apply guidelines to new code, or to existing code only
  when a file is under major change (do a separate *move* commit first).
- For deep security auditing, also use the `odoo-security` skill.

## Module structure & file naming

- Standard directories: `models/`, `views/`, `controllers/`, `data/`,
  `security/`, `static/`, and optional `wizard/`, `report/`, `tests/`,
  `populate/`.
- Split models by main model, one file per main model; each inherited model in
  its own file (`res_partner.py`). A single-model module's file matches the
  module name.
- Suffix conventions: backend views `*_views.xml`, portal/QWeb pages
  `*_templates.xml`, menus optional `*_menus.xml`, data `*_data.xml`, demo
  `*_demo.xml`, wizards `<transient>.py` + `<transient>_views.xml`.
- Security files: `security/ir.model.access.csv`, groups in `<module>_groups.xml`,
  record rules in `<model>_security.xml`.
- Controllers live in `<module>.py` (the old `main.py` is deprecated); inherited
  controllers in `<inherited_module>.py` (e.g. `portal.py`).
- File names use only `[a-z0-9_]`. Don't link external data by URL (images,
  libs) — copy it into the codebase.

### Manifest (`__manifest__.py`)

- `name` is required; `version` should follow semantic versioning.
- `depends` must list **every** module whose features/resources are used —
  including `base` (always installed, but list it so the module updates when
  `base` does).
- `data` files are always installed/updated; `demo` files load only in demo
  mode. Keep load order correct (a record's dependencies first).
- `license` defaults to `LGPL-3`; set it deliberately and correctly.
- `auto_install` is only for "link" modules (installed automatically when their
  dependencies are). `application` is `True` only for full apps, not technical
  modules. Declare non-Odoo requirements in `external_dependencies`
  (`python`/`bin`).
- `assets` declares how static files load into bundles (don't register assets
  ad-hoc elsewhere).

## Python — models & ORM

### Imports

- Three groups, each alphabetically sorted: (1) stdlib/external libs,
  (2) `odoo` submodules (`from odoo import Command, _, api, fields, models`),
  (3) `odoo.addons.*` (rarely, only if necessary).

### Naming & method conventions

- Model `_name`: dotted, prefixed by module, **singular** (`sale.order`, not
  `sale.orders`). Transient/wizard: `<base_model>.<action>` (avoid the word
  "wizard"). SQL-view report model: `<base_model>.report.<action>`.
- Python classes use PascalCase (`class AccountInvoice(models.Model)`).
- Variables: a model class var is PascalCase (`Partner = self.env['res.partner']`);
  ordinary vars are lowercase_underscore. Suffix a var holding a record id /
  list of ids with `_id` / `_ids` (don't name a `res.partner` record
  `partner_id`).
- Method-name patterns: compute `_compute_<field>`, search `_search_<field>`,
  default `_default_<field>`, selection `_selection_<field>`, onchange
  `_onchange_<field>`, constraint `_check_<name>`, object action `action_*`
  (acts on one record — start it with `self.ensure_one()`).
- Model body order: private attrs (`_name`, `_description`, `_inherit`) → default
  methods → field declarations → SQL constraints/indexes → compute/inverse/search
  (field order) → selection methods → `@api.constrains`/`@api.onchange` → CRUD
  overrides → action methods → other business methods.

### ORM idioms & correctness

- Use recordset methods (`filtered`, `mapped`, `sorted`) for readability and
  performance; prefer them over manual loops.
- Recordsets/collections are booleans: write `if records:` / `if some_list:`,
  not `if len(...)`.
- `create` must accept a list of vals (`@api.model_create_multi`); don't call
  `create` per record in a loop (see Performance).
- `@api.depends` must list **every** field the compute reads; stored computes
  need correct dependencies and no side effects.
- `@api.onchange` is UI-only — never rely on it for data integrity; enforce
  invariants with `@api.constrains` / SQL constraints.
- Propagate context with `with_context(...)` (it's a frozendict, immutable);
  name custom context keys carefully and prefix module-specific ones (a stray
  `default_<field>` in context leaks into unrelated `create` calls).
- Keep methods small and **extendable**: factor domains/criteria into overridable
  helpers (`self._get_partner_domain()`) instead of hardcoding business logic in
  one long method.
- Don't read a non-relational field on a multi-record set (it raises) — iterate
  or `mapped`. Conversely, guard single-record assumptions with `ensure_one()`.
- Delegation inheritance (`_inherits`) inherits fields but **not** methods; avoid
  it where you can (chained `_inherits` is unsupported).
- **Never** call `cr.commit()` / `cr.rollback()` unless you opened your own
  cursor; the framework owns the transaction. Any unavoidable commit needs an
  explicit comment justifying it.
- Catch **specific** exceptions over the smallest possible block; let unexpected
  ones propagate to the framework. To recover from framework exceptions, wrap the
  work in `with self.env.cr.savepoint():` (note: >64 savepoints per transaction
  degrades PostgreSQL — bound batch sizes).

### Translations with `_()`

- Use `self.env._('literal string')` only on **static** literals; field values
  are translated via the field's `translate` flag, not `_()`.
- Pass interpolation as arguments — `_('Record %s cannot be modified', record)` —
  never format before/after (`_('...%s' % x)` and `_('...%s') % x` both break
  translations). No string concatenation or dynamic strings inside `_()`.
- Prefer `%` over `.format()`, and named `%(name)s` over positional when there are
  several variables, so translators keep placeholders straight.

## Fields

- Relational suffixes: `Many2one` → `_id`, `One2many`/`Many2many` → `_ids`.
- Add `index=True` to fields that are searched/filtered — but not to every field
  (indexes cost space and slow `INSERT`/`UPDATE`/`DELETE`).
- Restrict sensitive fields with the `groups` attribute (comma-separated external
  ids); restricted fields are dropped from views and `fields_get`, and raise on
  direct read/write.
- Check relational definitions: correct `comodel_name`, sensible `ondelete`,
  `required`, and a currency companion for monetary fields.
- Use **reserved** fields for their built-in behavior rather than reinventing
  them: `active` for archiving (via `action_archive`, not a custom boolean),
  `state` for lifecycle, `parent_id` + `parent_path` (`index=True`, with
  `_parent_store`) for trees, `company_id` for multi-company (consistency via
  `_check_company`). Keep `_log_access` enabled on a `TransientModel`.
- A field and a method can't share a name (same namespace) — flag collisions.
- `related` fields can't chain `One2many`/`Many2many` in the dependency path;
  reach the target through a `Many2one`. Reusing one compute for several fields
  is fine; reusing one **inverse** for several is not.

## Controllers (HTTP routes)

- Routes are methods decorated with `@route` on a `http.Controller` subclass.
  When **overriding** a route, you must re-decorate with `@route` or the method
  becomes unpublished; an empty `@route()` keeps the parent's arguments, and any
  argument overrides the previous one.
- Set the right `auth` on each route (`user`, `public`, or `none`): a `public`
  route must not expose internal data or perform privileged writes (see the
  Security section and the `odoo-security` skill).

## XML — views, actions, data

- Record format: put `id` before `model`; inside a `field`, `name` first, then
  the value (tag body or `eval`), then other attributes by importance. Group
  records by model.
- Prefer the syntactic-sugar tags `<menuitem>` and `<template>` over raw
  `<record>` for menus and QWeb views.
- `<data noupdate="1">` only for non-updatable data; if the whole file is
  noupdate, set `noupdate="1"` on `<odoo>` and drop `<data>`.
- XML id patterns: view `<model>_view_<type>` (`form`/`list`/`kanban`/`search`),
  action `<model>_action[_<detail>]`, window-action view
  `<model>_action_view_<type>`, menu `<model>_menu[_<do_stuff>]`, group
  `<module>_group_<name>`, rule `<model>_rule_<group>`. The record `name` mirrors
  the id with dots instead of underscores; actions get a real display name.
- Inheriting views: reuse the **same xml id** as the original record; the `name`
  carries an `.inherit.<details>` suffix. A new **primary** view sets
  `mode="primary"` and needs no inherit suffix.
- Inherit via stable `xpath` (match on `name`/attributes); avoid brittle
  position-only matching. Don't duplicate fields already present.

## QWeb reports (PDF)

- A custom report's `_get_report_values` must add the default `docs` / `doc_ids`
  / `doc_model` itself if the template needs them — they are not auto-included.
- For translated reports use `t-lang`; only re-browse records in the target
  language when the template reads translatable fields (otherwise it is a
  needless performance cost).

## CSV & security data

- `ir.model.access.csv`: access rights are **additive** (a user's access is the
  union over their groups). An empty `group_id` grants the ACL to *every* user,
  including portal/public — flag accidental public create/write/unlink. The
  `perm_read/write/create/unlink` flags are all off by default.
- `ir.rule` record rules are conditions evaluated per record, default-allow.
  **Global** rules (no group) *intersect* (each added rule restricts further and
  risks non-overlapping rulesets that lock everyone out); **group** rules *unify*.
  For rules, an unselected `perm_*` means the rule simply doesn't apply to that
  operation.
- Sensitive models should have record rules; multi-company models need company
  rules (`company_ids`).

## JavaScript & static assets

- Organize under `static/`: libraries in `static/lib/<lib>/`, source in
  `static/src/{js,scss,xml}`, end-user tours in `static/src/js/tours`, tests in
  `static/tests` (test tours in `static/tests/tours`). One component per file
  with a meaningful name; QWeb templates rendered in JS go in `static/src/xml`.
- Baseline: run a linter, never add **minified** JS libraries, PascalCase class
  names. Register assets through the manifest's asset bundles, not ad-hoc.
- OWL components: do initialization in `setup()`, not the constructor.
- Talk to the server through the `orm` service (obtained via hooks like
  `useService`), not ad-hoc `fetch`/RPC; avoid extra client-server round-trips.
- Translate static JS strings with `_t` (same discipline as the server `_()`:
  literals only, no concatenation).
- Patching (`patch`) is a last resort — it's dangerous, apply it as early as
  possible; prefer registries or component inheritance.
- Templates (QWeb/OWL): render with `t-out` (escapes by default), never `t-raw`
  (a common XSS vector); separate structure from injected content rather than
  concatenating HTML. The old QWeb inheritance mechanism is deprecated.
- Parse data with `JSON.parse` (JS) — never `eval`.

## SCSS & CSS

- Formatting: 4-space indent (no tabs), ~80-column lines, opening brace on the
  selector line, closing brace on its own line, one declaration per line.
- Order properties from the outside in (start at `position`, end with decorative
  rules like `font`/`filter`); put scoped SCSS and CSS variables at the top,
  separated by a blank line.
- Class naming: avoid `id` selectors; prefix classes with `o_<module>` (just
  `o_` for the webclient). Use the flat "grandchild" approach
  (`o_element_entry`), not hyper-specific nested names.
- Variable conventions: SCSS `$o-[root]-[element]-[property]-[modifier]`, scoped
  SCSS `$-[name]`, mixins/functions `o-[name]` (imperative verbs), CSS variables
  in BEM `--[root]__[element]-[property]--[modifier]`. Don't define CSS variables
  on `:root` (use SCSS for global design); CSS variables are for contextual DOM
  adaptation.

## Security (review essentials — see the `odoo-security` skill for a full audit)

- Any **public** method is callable via RPC with arbitrary arguments; `self` and
  params can't be trusted (ACL is only enforced on CRUD). Keep internal helpers
  `_`-prefixed, and still validate inputs.
- Don't bypass the ORM with the raw cursor (you lose access rights, translations,
  invalidation). Build SQL with the `SQL` wrapper or parameters (`%s` + args) —
  **never** `+`/`%` string interpolation.
- Build domains with `fields.Domain`, not by concatenating lists (avoids domain
  injection).
- Avoid `eval`; for trusted privileged use only, `safe_eval`; otherwise parse with
  `int()`/`float()`/`json.loads()`/`ast.literal_eval()`.
- Read dynamic field values via `record[field_name]`, not `getattr` (which exposes
  private attrs/methods). Use `sudo()` narrowly and deliberately, never to mask an
  access bug.

## Performance

- **Batch, don't loop queries.** Replace `search_count` per record with one
  `_read_group`; accumulate `create` values and create the batch once; `browse`
  the whole recordset before the loop so fields prefetch in a single query.
- **Reduce complexity.** Pre-map results into a dict (`{r['id']: r}`) instead of
  nested loops; cast membership-test collections to `set` (or use recordset
  arithmetic like `self - invalid`) to avoid O(n²).
- Index searched fields (`index=True`) — selectively, per the Fields section.

## Tests

- Use `TransactionCase` (or `HttpCase` for web), tag classes with `tagged`, and
  assert behavior rather than implementation. Guard query counts with
  `assertQueryCount` for performance-sensitive paths.
- `at_install` and `post_install` are mutually exclusive; use `post_install` for
  tests that need the fully-loaded registry. Tests run only for installed
  modules.
- A test tour's last step must leave the client in a stable state (no pending
  edits or in-flight requests) to avoid teardown race conditions.
