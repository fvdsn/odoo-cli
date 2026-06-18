---
name: odoo-security
description: >-
  Security review of Odoo module code: access rights and record rules, SQL
  injection, unsafe sudo/privilege escalation, controller auth, unsafe
  deserialization/eval, and template/XSS issues. Use when auditing an Odoo
  addon for security.
---

# Security review of Odoo code

Audit Odoo addons for the framework-specific ways access control and injection
go wrong. Report findings with file/line and a concrete fix; do not weaken
security to make something work.

## Access control

- Every model has `ir.model.access.csv` entries scoped to the right groups;
  no accidental public/`base.group_user` write/unlink access.
- Sensitive models have **record rules** (`ir.rule`) for row-level access;
  multi-company models have company rules.
- `sudo()` is the top risk: each use must be justified and narrow. Flag `sudo()`
  that runs on user-supplied ids/domains, or that bypasses a rule the feature is
  supposed to enforce.
- `with_user`/`with_company` switches are intentional and not attacker-control.

## Injection and unsafe execution

- No SQL built with f-strings/`%`/`.format`; raw `cr.execute` must use
  parameters (`%s` + args tuple), never string concatenation of input.
- No `eval`/`exec`/`safe_eval` over user-controlled input; if `safe_eval` is
  used, inputs and `globals`/`locals` are constrained.
- No unsafe deserialization (`pickle`, `yaml.load` without `SafeLoader`) of
  untrusted data.

## Controllers and web

- `@http.route` uses the correct `auth` (`user`/`public`/`none`) — `public`
  routes must not expose internal data or perform privileged writes.
- `csrf=True` for state-changing POST routes; no disabling CSRF without reason.
- Domains/ids/fields coming from request params are validated; no reading
  arbitrary models/records by user-supplied `model`/`id`.
- QWeb output of user data is escaped (no `t-raw`/`markupsafe` on untrusted
  content); file downloads set safe content types and names.

## Secrets and data exposure

- No secrets/tokens committed or logged; system parameters used for config.
- Error paths don't leak stack traces or internal data to unauthenticated
  users.

## How to work

- Start from `ir.model.access.csv`, `security/*.xml` (record rules), and every
  `@http.route` and `sudo()` in the module.
- For each finding give severity, the exact location, and the minimal fix.
