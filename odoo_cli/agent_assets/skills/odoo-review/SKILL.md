---
name: odoo-review
description: >-
  Review Odoo module code (models, fields, views, controllers, manifests) for
  framework correctness and conventions: ORM usage, field/compute/onchange
  patterns, security records, view XML, and performance. Use when reviewing or
  writing code in an Odoo addon.
---

# Reviewing Odoo code

Review against Odoo's framework conventions, not generic Python style alone.
Focus on the issues that actually bite in Odoo addons.

## ORM and models

- No SQL string interpolation; use the ORM, or parameterized `self.env.cr`
  queries. Never build queries with f-strings/`%`.
- Avoid queries and writes inside loops over recordsets; operate on recordsets
  (batch `search`/`read`/`write`), and read related fields via the ORM rather
  than per-record round-trips.
- `create` should accept and handle lists (`@api.model_create_multi`); avoid
  per-record `create` in loops.
- Respect `depends`/`compute`/`inverse`/`search` contracts: `@api.depends` lists
  every field read; stored computes have correct dependencies; no side effects
  in computes.
- `@api.onchange` is UI-only — do not rely on it for data integrity; enforce
  invariants with constraints (`@api.constrains`, SQL constraints).
- Use `sudo()` deliberately and narrowly; never to paper over an access bug.
- Translations: wrap user-facing strings with `_()`; do not interpolate before
  translating.

## Fields and manifests

- Field definitions: correct `comodel_name`, `ondelete`, `required`, `index`
  where queried; monetary fields pair with a currency field.
- `__manifest__.py`: accurate `depends` (every model/view/feature used), correct
  `data`/`assets` ordering, sane `license` and `version`.

## Views and assets

- XML views: stable `id`s, correct `inherit_id` + `xpath` (avoid brittle
  position matching), no duplicated fields, groups/access respected.
- Assets registered through the manifest's asset bundles, not ad-hoc.

## Tests and migrations

- Tests use `TransactionCase`/`HttpCase` and tagged appropriately; assert
  behavior, not implementation.
- Schema changes ship with the right migration or rely on Odoo's update path
  (`odoo update <module>`).

## How to work

- Read the module's `__manifest__.py` first to understand scope and deps.
- Run `odoo test <module>` and `odoo update <module>` to check the change loads
  and applies cleanly. Flag, don't auto-fix, anything ambiguous.
