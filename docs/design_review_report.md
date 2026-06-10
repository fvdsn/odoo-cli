# Odoo CLI design review report

This report reviews the current `docs/` design after the v1/v2/v3 rewrite.
It is written as feedback for another design pass, not as an implementation
plan.

## Executive summary

The current design is materially cleaner than the previous `workspace.toml`
design. The strongest improvement is the move toward derived state:

- worktrees are discovered from the filesystem
- repository enablement is the presence of `.repositories/*.git`
- worktree versions come from `odoo/odoo/release.py`
- installed modules come from the database
- ports live in `.run/{worktree}/{db}/ports`
- the CLI avoids storing a parallel model of Odoo state

That direction is good. It makes the tool easier to explain, easier to debug,
and less likely to develop contradictory sources of truth.

The main remaining risks are lifecycle edges. The design now says "derive
everything" very strongly, but some actions still need ownership rules:
database creation, shared `odoo.conf` modification, port reservation, Python
interpreter selection, and optional repository side effects. Those are fixable
before implementation.

My overall recommendation is: proceed with this direction, but tighten the v1
spec around the points below before writing much code.

## Things that are working well

The v1 scope is much more realistic now. Foreground-only `odoo start`, no
background lifecycle, no `status`, no `log`, no `rpc`, no `doctor`, and no cloud
backend all make sense for an internal first version.

Deferring the formal backend abstraction is a good call. A backend interface
designed before a second backend exists would likely be wrong. Keeping only an
injectable process-runner seam in v1 is a better tradeoff.

The `OdooBinService` boundary is important and should stay. It gives one owner
for translating odoo-cli concepts into `odoo-bin` invocations, including
version-dependent behavior and future delegation when `odoo-bin` adopts the same
conventions.

The split between v1, v2, and v3 is clear. v1 proves the local workflow, v2 adds
operational comfort, and v3 becomes the platform layer for MCP/cloud/extensions.

The linked worktree model is now understandable: symlinked standard repos,
real addon repo worktrees, and no stored addon list. That is a good answer to
the support-team disk usage concern.

## High-priority issues

### 1. Database lifecycle is inconsistent

The docs currently imply several different lifecycle rules:

- `odoo init` creates an empty database
- `odoo start` creates/initializes the database on first start
- the first-use flow runs `odoo module install crm` before `odoo start`
- `odoo module install` delegates to `odoo-bin module install`, which requires
  an initialized database

This needs one explicit rule.

Recommended rule:

> Any odoo-cli command that needs an initialized database should initialize the
> target database if it does not exist yet, unless the command is explicitly
> read-only.

That means `odoo module install crm` can be the first command after `odoo init`,
which keeps the happy path pleasant:

```bash
odoo init
odoo module install crm
odoo start
```

Implementation-wise, `DatabaseService` should own `ensure_initialized(target)`.
`ModuleService`, `ServerService`, `UpdateService`, `ShellService`, and
`TestingService` can call it when appropriate.

Important wording change:

> `odoo module install` delegates to `odoo-bin module install` when available;
> for supported Odoo versions where that command does not exist yet,
> `OdooBinService` polyfills the behavior with the appropriate legacy
> invocation.

Do not describe `odoo-bin module install` as universally existing.

### 2. Shared `~/.config/odoo/odoo.conf` needs lifecycle rules

Using Odoo's standard `odoo.conf` is a strong simplification, but it is also the
boldest design choice. The file is user-global and may already exist.

The spec should define:

- what `odoo init` does when `~/.config/odoo/odoo.conf` already exists
- whether it merges, backs up, refuses, or asks the user
- whether `odoo config set` preserves unknown keys
- whether comments are intentionally lost when `configparser` rewrites the file
- whether the CLI writes a generated-section marker
- how `ODOO_RC` and `~/.odoorc` warnings should be phrased

Recommended v1 rule:

> `odoo init` creates `~/.config/odoo/odoo.conf` if missing. If it already
> exists, it preserves unknown keys, updates only known keys when explicitly
> requested, and prints a warning that comments may not be preserved by
> `odoo config set`.

If preserving comments matters, `configparser` is the wrong writer. If
preserving comments does not matter in v1, the destructive formatting behavior
should be documented plainly.

### 3. Manual `odoo-bin` equivalence is overstated

The design says the shared standard config keeps manual `odoo-bin` runs aligned
with odoo-cli. That is true only for the base config.

Manual `odoo-bin` runs will not automatically get:

- computed `addons_path`
- derived database name
- allocated ports
- future per-instance data dir

Until those conventions migrate into `odoo-bin`, the more precise claim is:

> Manual `odoo-bin` runs share the same base `odoo.conf`; `odoo where` shows the
> full resolved command needed to reproduce an odoo-cli run.

This still supports the thin-wrapper philosophy without promising more than v1
can deliver.

### 4. CLI Python and Odoo venv Python are different problems

The CLI itself can target Python 3.11+ / Debian Bookworm+. But Odoo worktrees may
require different Python versions. The current master checkout, for example,
declares `MIN_PY_VERSION = (3, 12)` and `MAX_PY_VERSION = (3, 14)` in
`odoo/odoo/release.py`.

The venv strategy should explicitly say that `VenvService`:

- reads `MIN_PY_VERSION` and `MAX_PY_VERSION` from `release.py`
- finds a compatible interpreter for that specific worktree
- creates the venv with that interpreter
- fails with an actionable error if no compatible interpreter is available
- does not assume the CLI interpreter is suitable for Odoo itself

This will matter a lot on Debian Bookworm, where the CLI may run on Python 3.11
while newer Odoo versions may require Python 3.12+.

### 5. `odoo repo enable` needs exact v1 flags

`odoo repo enable enterprise` is side-effecting: it clones/fetches the repo and
may modify existing worktrees. The docs currently say this can be scoped "with a
flag", but the flags are not defined.

Since this is v1, define the grammar now.

Possible shape:

```bash
odoo repo enable enterprise
odoo repo enable enterprise --future-only
odoo repo enable enterprise --worktree 19.0 --worktree my-feature
```

Recommended default:

> Enable for future worktrees and add to all compatible existing worktrees,
> skipping incompatible versions with warnings.

That default is convenient, but because it mutates many worktrees it must print
a clear summary:

- cloned/fetched repo
- worktrees updated
- worktrees skipped
- reason for each skip

### 6. `odoo worktree create master` needs grammar clarification

The use cases show:

```bash
odoo worktree create master
```

The requirements also say:

```bash
odoo worktree create my-feature
```

is invalid because the version would be ambiguous.

These can both be true, but the grammar needs to say so.

Recommended rule:

> With one positional argument, `odoo worktree create X` means
> `name=X, version=X`, and is valid only if `X` resolves to an Odoo ref/version.
> With two positional arguments, `odoo worktree create NAME VERSION` creates
> worktree `NAME` from `VERSION`.

Then `master`, `19.0`, and `saas-19.4` work as single-argument forms, while
`my-feature` fails unless there is actually a branch/ref named `my-feature`.

## Medium-priority issues

### 7. `.claude/` by default feels too vendor-specific

The default workspace layout includes `.claude/`. For an official Odoo tool,
that is surprising unless this is explicitly an Anthropic-oriented installer.

Options:

- make agent files opt-in
- generate a vendor-neutral `.agents/` directory
- move `.claude/` creation to an extension
- create it only when the user passes an agent-specific flag

Because the tool is meant to be the default way to develop Odoo, I would avoid a
vendor-specific directory in the default workspace unless there is a strong
product reason.

### 8. Port reservation needs atomic semantics

The port design is good: stable ports per `(worktree, db)`, no silent
reassignment, smallest-free allocation, and one shared reservation pool for http
and gevent.

The spec should add atomicity rules:

- lock while choosing/writing ports
- write temp file then rename
- if final bind fails, remove or roll back a newly-created reservation
- if the reservation already existed, leave it unchanged
- define stale reservation behavior separately from stale worktree behavior

Without this, concurrent starts and failed starts can leave confusing port files.

### 9. Duplicate addon module names need behavior

The addons path order is deterministic:

1. `odoo/addons`
2. `themes`
3. `enterprise`
4. custom addon paths alphabetically

That is good, but duplicate module names across paths can be very confusing.

The spec should say whether the CLI:

- warns
- errors
- ignores duplicates and relies on Odoo

Recommended rule:

> On commands that run Odoo, detect duplicate addon module names in the resolved
> addons paths and fail with a concise diagnostic unless an explicit escape hatch
> is passed.

Silent shadowing would be painful during daily development.

### 10. V1 command count should be normalized

The docs say "v1 (12 commands)", but the listed surface can be counted in
multiple ways:

- top-level commands
- command groups
- subcommands

This is minor, but it creates avoidable ambiguity. Either remove the number or
define what is being counted.

### 11. Foreground-only v1 affects testing and use cases

The e2e section says to start the foreground server and later stop it, but v1 has
no `odoo stop`. The test plan should say how foreground server e2e works:

- spawn `odoo start` as a subprocess
- wait for the allocated port
- terminate the subprocess from the test harness
- assert `.run/.../ports` behavior

Do not phrase this as using `odoo stop` in v1.

### 12. Config secrets and v2 app credentials need a clearer destination

v1 has only the PostgreSQL password. v2 wants configurable Odoo login
credentials, "likely stored in `odoo.conf`". This should stay open for now, but
the docs should be careful: `admin_passwd` is not the admin user's password.

Potential v2 options:

- custom `odoo.conf` keys for development credentials
- separate keyring support
- environment-only secrets
- per-worktree/per-db credential file

No need to solve this in v1, but do not casually overload existing Odoo keys.

## Low-priority cleanup

### 13. Click vendoring wording differs between docs

The requirements say Click is available as Debian `python3-click`; the
architecture says upstream vendors Click and Debian may unvendor it.

These are compatible, but should be phrased the same way:

> Upstream distributions vendor Click so the bash installer only needs Python.
> Debian/Ubuntu packages may unvendor and depend on `python3-click`.

### 14. `odoo rpc` references v1 defaults while rpc is v2

`requirements_v2.md` says v1 does not manage Odoo credentials and `odoo rpc`
assumes `admin` / `admin`, but `odoo rpc` itself is v2. The intended meaning is
clear, but the wording should be adjusted:

> When `odoo rpc` lands in v2, it initially defaults to `admin` / `admin` unless
> configurable credentials are implemented at the same time.

### 15. Repository URL derivation should define missing remote behavior

Repositories are derived from `.repositories/*.git` and their `origin` remote.
Define what happens if a bare repo exists without `origin`:

- allowed for local/manual setups?
- shown as `url = None`?
- rejected by commands that need fetch?

The architecture hints at `url: str | None`; the requirements should say what
that means operationally.

### 16. Blobless clone behavior should be surfaced in failure messages

Blobless clones are a good default for speed, but first blame/checkout of a new
ref may need network. The docs mention this. The implementation should make
network-related failures explain that the repository may be partial/blobless.

## Suggested spec edits

These are the concrete text-level changes I would make.

### Database auto-init

Add to "Database names managed by convention" or "Installed apps":

```text
Commands that need an initialized database call DatabaseService.ensure_initialized().
If the target database does not exist, it is created and initialized empty
before the command continues. Read-only commands fail with a clear "database
does not exist" message instead.
```

### Module install delegation/polyfill

Replace:

```text
wraps the existing `odoo-bin module install` command
```

with:

```text
delegates to `odoo-bin module install` when available; for supported Odoo
versions where it is not available, `OdooBinService` polyfills the behavior with
the appropriate legacy invocation.
```

### Shared config wording

Replace the broad manual-run claim with:

```text
Manual `odoo-bin` runs share the same base `odoo.conf`. The full resolved
runtime command also includes CLI-computed values such as addons path, database,
and ports; use `odoo where` to inspect or copy that command.
```

### Python interpreter rule

Add to "Venv strategy":

```text
The CLI's Python interpreter and the Odoo venv interpreter are resolved
separately. For each worktree, the CLI reads the supported Python range from
`odoo/odoo/release.py`, finds a compatible interpreter, and creates the venv
with it. If none is found, the CLI fails with installation instructions for the
platform.
```

### Worktree create grammar

Add to `odoo worktree create`:

```text
One positional argument means both name and version/ref. It is valid only when
that argument resolves to an Odoo ref/version. Two positional arguments mean
explicit name plus version/ref.
```

## Final assessment

The current plan is moving in the right direction. It is closer to a
Cargo-quality CLI now than the earlier design because it removed a lot of
parallel configuration and made the filesystem/database/runtime state the source
of truth.

The design is not overengineered at the moment. If anything, the recent rewrite
removed abstractions: no `workspace.toml`, no formal backend interface in v1, no
background lifecycle in v1, no status/log/rpc in v1, no per-instance data in v1.

The risk is not architecture size; the risk is underspecified lifecycle behavior
around a small number of side-effecting commands. If those are nailed down
before implementation, this is a strong foundation for a pleasant daily Odoo
development tool and a future agent/cloud platform.
