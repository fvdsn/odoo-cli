---
name: odoo-security
description: >-
  Security review of Odoo module code: access rights and record rules, field
  access, untrusted public methods/RPC, SQL and domain injection, unsafe
  sudo/privilege escalation, controller auth/CSRF, eval, file access, unsafe
  deserialization, returning complex objects, getattr/setattr, timing attacks,
  and XSS/escaping. Use when auditing an Odoo addon for security.
---

# Security review of Odoo code

Audit Odoo addons for the framework-specific ways access control and injection
go wrong, using Odoo's two data-driven mechanisms (access rights + record rules)
and the documented pitfalls below. Report each finding with severity, exact
file/line, and a minimal fix. **Never weaken security to make a feature work.**

## Access rights (`ir.model.access.csv`)

- Grant CRUD on a whole model to a group. Access is **additive**: a user's
  rights are the union across their groups; no matching ACL = denied.
- `perm_read`/`perm_write`/`perm_create`/`perm_unlink` are **off by default**.
- An **empty `group_id` grants the ACL to every user**, including portal and
  public users — flag accidental public/portal `read`/`write`/`create`/`unlink`,
  and fine-tune ACLs that reach `base.group_portal`/`base.group_public`.

## Record rules (`ir.rule`)

- Row-level conditions evaluated **after** access rights, **record by record**;
  default-allow. `domain_force` is a Python expression with `time`, `user`
  (singleton recordset), `company_id`, and `company_ids`.
- The rule's `perm_*` select **which operations the rule applies for**; an
  unselected operation is not checked. A rule that protects only some operations
  (e.g. `read` but not `write`) leaves the others open — cover **all** CRUD ops
  that need restricting, or an attacker can `write` to enumerate/alter records a
  `read` rule was meant to hide.
- **Global** rules (no group) combine with **AND** (each one restricts further;
  non-overlapping globals can remove all access). **Group** rules combine with
  **OR** (any matching group rule suffices); the global+group sets intersect.
- Sensitive models need rules; multi-company models need company rules via
  `company_ids` / `_check_company`.

## Field-level access

- A field's `groups` attribute (comma-separated external ids) removes it from
  views and `fields_get` and raises on explicit read/write. Use it for sensitive
  fields instead of relying on the UI to hide them.
- **Passwords and API tokens**: restrict them with `groups="base.group_system"`
  (or restrict the whole model's ACL). A token field on a model with a permissive
  ACL is readable by any user via `search_read`.
- Beware **writable `related` fields** that reach into another model
  (`related='partner_id.email', readonly=False`): writing the source M2o then
  reading the related field can dump data the user shouldn't see, and the related
  value may be computed with elevated rights.

## Pitfalls

### Default to private methods

- **Any public method is callable via RPC** with attacker-chosen arguments; the
  records in `self` and the parameters **cannot be trusted** (ACL is only
  enforced on CRUD, not method calls). More public methods = bigger attack
  surface. **Prefix methods with `_` by default**; drop the `_` only when the
  method is genuinely meant to be called externally — and then validate inputs.
  (Privacy alone isn't a control: a `_`-method fed untrusted data is still
  dangerous.)

### Use the ORM; parameterize SQL

- Never use the cursor directly when the ORM can do it: raw SQL bypasses access
  rights, record rules, translations, field invalidation, and `active` handling.
  Prefer `search`/`read_group`/`browse(...).read(...)`.
- When you must write SQL, **never** interpolate with `+`/`%`/`.format`. Pass
  values as **parameters** (psycopg2 formats them, including a tuple for
  `IN %s`), or use the `odoo.tools.SQL` wrapper. For dynamic **identifiers**
  (table/column names, which can't be parameters) use `SQL.identifier(name)` —
  it validates the name and prevents injection that `.format` would allow.

### Domain injection

- Build/extend domains with `fields.Domain` (`domain &= Domain(...)`), never by
  concatenating a user-provided list onto a security domain (a user could inject
  `['|', ...]` to widen access).

### Don't over-`sudo`

- `sudo()` is the top risk — review every use twice, especially in controllers
  and public methods, never use it to mask an access error. For each `sudo()`,
  confirm there is no attacker-controlled:
  - **read**: arbitrary model / record / field;
  - **create**: arbitrary model / values;
  - **write**: arbitrary model / record / values;
  - **search**: arbitrary model / domain / injection.
- Controllers: never `record.sudo().write(post)` with raw request params —
  whitelist keys (`{k: post[k] for k in ('name', 'email') if post.get(k)}`).
- Avoid sudo-computed `related` fields onto `ir.attachment` (arbitrary
  `attachment_id` → arbitrary file read). Prefer a plain `fields.Binary`, or
  create/search `ir.attachment` records so the ORM enforces its access rights.
- `with_user` / `with_company` switches must be intentional, not attacker-driven.

### Require POST + CSRF for state changes

- A route that writes must use `methods=['POST']` and keep CSRF on (never
  `csrf=False`, except dedicated webhooks). State-changing logic on a **GET**
  route is a CSRF hole: an attacker can auto-submit a hidden form / crafted link
  and perform the action as the logged-in victim.
- Templates that POST must include `<input type="hidden" name="csrf_token"
  t-att-value="request.csrf_token()"/>`.

### Prevent XSS (escape on the way into the DOM)

- Reflected (script in URL/params) and stored (script saved by a low-privileged
  user) both execute with the victim's session — far more than `alert()`.
- Server/QWeb: render with `t-out` (escapes by default), never `t-raw`; OWL
  templates use `t-out`. Build HTML by wrapping **literals** in
  `markupsafe.Markup` and formatting user content in (Markup auto-escapes;
  `escape()`/`html_escape` turns `str` into escaped `Markup`). f-strings defeat
  escaping (`Markup(f"<p>{x}</p>")`) — use `Markup("<p>{x}</p>").format(x=...)`.
  `_()` escapes when any argument is `Markup`, so keep HTML out of the literal.
- JS: never concatenate user/low-privilege values into the DOM
  (`$el.html(...)`, `.append('<td>' + name + '</td>')`). Wrap with `Markup(...)`
  and `escape()` the variable parts, or render through OWL `t-out`.

### Escaping vs sanitizing

- **Escaping** (TEXT→CODE) is always mandatory when mixing data with code, even
  for trusted data. **Sanitizing** (CODE→safer CODE) is only for **untrusted**
  CODE and only works **after** escaping (sanitizing raw TEXT corrupts it).
  `fields.Html`/`html_sanitize` options (e.g. `strip_classes`) tune the level.

### Open files with `file_open`, not `open`

- Never use the builtin `open()` on a path that can be influenced — it can read
  *or write* arbitrary files on the host (config, ssh keys, executable Python →
  RCE). Use `odoo.tools.file_open()`, which confines access to the addons paths.

### `eval` is evil

- Never `eval`/`exec`. To parse data use `json.loads()` or `ast.literal_eval()`;
  only at worst `odoo.tools.safe_eval.safe_eval` with a constrained namespace,
  and only for trusted privileged users (it still gives broad capabilities, and
  plain `eval` allows `__import__('os').popen(...)` RCE).

### Don't return complex objects from model methods

- A model method is reachable via server actions/RPC; if it **returns** a rich
  object (e.g. a crypto certificate/key, a backend handle), an attacker can walk
  its internals (`._backend._ffi`, `__globals__`, …) to read files or run code.
  Don't factor such logic into a model method if not needed; use a standalone
  module-level function, or dunder-prefix the method name.

### `getattr`/`setattr` are not your friends

- Don't access record fields by dynamic name with `getattr`/`setattr` — it
  exposes private attributes and methods (`__class__` → `__globals__` →
  `__import__` → RCE). Use `record[name]` (safe `__getitem__`); still validate
  the record id and field name, otherwise restrict.

### Never `pickle`

- Builtin `pickle` executes arbitrary code on load (via `__reduce__`). Don't
  unpickle untrusted data. Store/exchange with `json`; if pickling is
  unavoidable use `odoo.tools.misc.pickle` (restricted).

### Timing attacks

- Compare secrets/tokens in constant time with `odoo.tools.consteq`, not `==`
  (which short-circuits and leaks length/content via timing). Better, look the
  token up in the database (`search([('access_token', '=', token)])`).

### Mutable default arguments

- Don't use mutable default parameters (`def f(x, vals=[])`); they persist across
  calls and can leak/accumulate data.

## Audit checklist

- `cr.execute()` → can the ORM do it? else query parameters / `SQL` wrapper
  (`SQL.identifier` for identifiers).
- `sudo()` → no arbitrary model/record/field/value/domain.
- ACLs & record rules → global (AND) vs group (OR), every CRUD op covered,
  portal/public restricted.
- passwords/tokens → `groups="..."` or restricted ACL.
- `@route` that writes → POST, no `csrf=False` (except webhooks).
- XSS → `t-out` / `Markup(...)` + `escape()`, never `t-raw` or `$el.html(raw)`.
- `open()` → `file_open()`.
- `eval()` → `json.loads` / `ast.literal_eval` / `safe_eval`.
- complex objects → standalone or dunder method, no needless factorization.
- `getattr`/`setattr` → `record[name]`, otherwise restrict.
- `pickle` → `json` / `odoo.tools.misc.pickle`.
- secret comparison → `consteq`.

## How to audit

- Sweep `security/ir.model.access.csv`, `security/*.xml` (rules + groups), and
  every `@http.route`, `sudo()`, raw `cr.execute`/`SQL`, `t-raw`/`$el.html`,
  `open(`, `eval`/`safe_eval`/`pickle`, `getattr`/`setattr`, and secret/token
  comparison.
- For each finding: severity, exact location, and the minimal fix.
