# Odoo CLI requirements

## Supported platforms
 - Linux / MacOS / Windows WSL

## Supported python installation types
 - native packages with apt
 - venv with uv

## Supported Odoo versions
 - the CLI supports the Odoo versions Odoo itself currently supports, plus master
   (today: 17.0, 18.0, 19.0, master) — a self-updating definition that tracks
   Odoo's own support policy
 - a version counts as supported only when it is covered by the odoo-bin
   capability table and by the nightly e2e matrix
 - older versions fail early with a typed `UnsupportedOdooVersion` error rather
   than undefined behavior

## Primary installation path
 - `uv tool install odoo-cli-official` (recommended)
   - the PyPI name `odoo-cli` is squatted by a third party; publish as
     `odoo-cli-official` while pursuing a PEP 541 name transfer, then publish
     under `odoo-cli` as well
   - the installed executable is `odoo` regardless of the distribution name
 - `apt install odoo-cli` (Debian/Ubuntu; the apt namespace is unaffected)
 - `curl https://www.odoo.com/install.sh | bash` (fallback)
    -> working setup no questions asked
        -> fine-tune afterwards with `odoo config set` (interactive wizard is v2)
    -> no more than 5min
    -> the script lives at `install.sh` in this repo: it announces what it
       will install, ensures Python 3.10+ and git (apt/Homebrew), downloads
       the latest wheel from PyPI (sha256-verified), unpacks it under
       `~/.local/share/Odoo/cli` with a launcher at `~/.local/bin/odoo`, then
       runs `odoo init`; no pip, no venv, no third-party tooling, and no
       confirmation prompts (sudo's password prompt is the consent point)

## Available as a global `odoo` command
 - you can run `odoo start` from any directory in the shell
 - supported shells: bash, zsh, fish

## Directory structure

```
~/.config/odoo/odoo.conf        <- shared Odoo config (outside the workspace, Odoo's standard location)
~/odoo/                         <- default workspace location (no config file of its own)
    .repositories/              <- bare git repos (shared object store)
        odoo.git                <- cloned by odoo init; its presence marks an initialized workspace
        documentation.git       <- cloned by odoo init
        enterprise.git          <- added via odoo repo enable
        themes.git              <- added via odoo repo enable
        upgrade.git             <- added via odoo repo enable
        customer-a-addons.git   <- added via odoo repo add
        support-tools.git       <- added via odoo repo add
    .venvs/                     <- one per odoo version (normalized from release.py)
        19.0/
        saas-19.4/              <- e.g. a master checkout; `~` normalized to `-`
    .run/                       <- ephemeral runtime state, per server instance
        master/                 <- worktree name
            master/             <- default db
                ports           <- v1: only this file (foreground server)
                pid             <- v2 (background lifecycle)
                log             <- v2
                socket          <- v2
                args            <- v2: sanitized start parameters (for restart)
            customer-a/         <- explicit db
                ports
                ...             <- pid/log/socket/args are v2
    .data/                      <- v2: persistent Odoo data, per database
        master/                 <- v1 uses odoo-bin's default data_dir instead
            master/                 (shared by all dbs/servers; not isolated)
                filestore/
            customer-a/
                filestore/
    19.0/                       <- full worktree (real git worktrees, pristine)
        odoo/                   <- always present
        documentation/          <- always present
        enterprise/             <- if added to this worktree
        themes/                 <- if added to this worktree
        custom-addon-repo-1/    <- custom addons live at the worktree root
        custom-addon-repo-2/
    customer-a/                 <- linked worktree
        odoo -> ../19.0/odoo
        documentation -> ../19.0/documentation
        enterprise -> ../19.0/enterprise
        customer-a-addons/      <- real git worktree from .repositories/customer-a-addons.git
        support-tools/          <- real git worktree from .repositories/support-tools.git
    my-feature/                 <- additional worktrees
        odoo/
        ...
```

## Workspace location
 - default: `~/odoo` — no questions asked, `odoo init` just creates it
 - a workspace root is identified by the presence of `.repositories/odoo.git`
   (the shared bare clone of Odoo); there is no marker config file
 - resolution order: `ODOO_DIR` if set, otherwise `~/odoo`
 - only one active workspace — multi-version is handled by worktrees, not multiple workspaces
 - if someone needs a second workspace, they set `ODOO_DIR` explicitly — no auto-discovery or parent-walking
 - cwd only matters for determining which worktree is targeted (if inside `~/odoo/my-feature/`, commands target that worktree; otherwise use `--worktree`, or rely on the only worktree if there is exactly one)

The workspace itself holds no configuration file. Everything a config file
would have held is either derived from the filesystem/git/database or stored in
the shared `odoo.conf` (see "Configuration via odoo.conf").

## Venv strategy
 - one venv per odoo version, shared across worktrees on the same version
 - rationale: the venv created from `requirements.txt` is often not enough for comfortable local dev; optional dependencies may be needed in practice, and developers should not have to recreate those additions for every worktree
 - venv creation installs a small set of pure-python extras alongside
   `requirements.txt`: `websocket-client` (drives the Chrome connection for
   browser/tour tests; without it every `HttpCase` tour is silently skipped)
   and `watchdog` (powers `--dev` autoreload, which the CLI enables by
   default via `dev_mode = all`)
 - venv creation also installs `rlPyCairo` — reportlab 4.x's barcode/QR PNG
   backend, which Odoo's requirements.txt omits (its Debian package covers
   it); pycairo ships no macOS/Linux wheels, so this is best-effort and
   gated on pkg-config finding the cairo system library (`odoo init`
   installs it)
 - version is determined by reading `odoo/odoo/release.py` in the worktree
 - the worktree version is never stored; the checked-out source is the source of truth
 - the resolved venv for a worktree is `.venvs/{version}`; there is no per-worktree venv override in v1
 - the venv directory name is the normalized detected version string (`~` replaced
   by `-`, e.g. `saas~19.4` → `saas-19.4`); there is no `master` venv — a master
   worktree uses whatever version its `release.py` reports
 - every command that runs odoo-bin ensures the resolved venv exists and creates
   it on demand; a pull can change the detected version (e.g. master rolling
   forward), which silently retargets the venv
 - venvs orphaned by rolled-forward versions are left in place; cleanup
   (`odoo venv prune` / `odoo doctor`) is a v2 concern
 - venvs are created with uv when it is on PATH, falling back to
   `python3 -m venv` + pip; the CLI itself never requires uv
 - the CLI's own interpreter and the venv interpreter are resolved separately:
   the supported Python range is read from the worktree's `odoo/odoo/release.py`
   (`MIN_PY_VERSION` / `MAX_PY_VERSION`) and a compatible interpreter is used to
   create the venv — never assume the interpreter running the CLI suits Odoo
 - when no compatible interpreter is installed, uv (when available) provisions
   one; otherwise fail with installation instructions for the platform
 - running without a venv at all (global apt python packages) is a v2 topic —
   see `requirements_v2.md`
 - `odoo venv` rebuilds the resolved venv for the current worktree when needed

## Everything odoo inside ~/odoo, nothing outside
 - one exception: the shared `odoo.conf` lives at Odoo's standard config
   location (see "Configuration via odoo.conf"), outside `~/odoo`

## Keep the repos pristine, don't abuse .gitignores

## Command idempotency and self-healing
 - commands are safe to interrupt (Ctrl-C, crash) and re-run: a re-run either
   completes the work or repairs the leftovers — it never loops on a broken
   intermediate state and never requires a manual `rm`/`dropdb` to escape
 - mutations prefer create-aside-then-rename: slow deletions never sit between
   the user and a usable state
 - recovery never deletes state that may hold user work; only artifacts
   provably created by an interrupted CLI run are removed automatically,
   anything else fails with a move-it-aside hint
 - "exists" is never trusted as "complete": bare repos are checked for a
   resolvable HEAD, databases for an initialized registry, venvs for their
   ready marker

## Configuration via odoo.conf (no workspace.toml)
 - there is no `workspace.toml`; the CLI keeps no parallel config file of its own
 - rationale: avoid duplicate state and avoid a second, competing source of
   configuration next to Odoo's own
 - most of what a config file would hold is already derivable and must not be
   stored:
   - repository list and URLs → read from `.repositories/*.git` and their git remotes
   - enabled/disabled repositories → presence of the bare repo (cloned = enabled)
   - venvs → presence under `.venvs/{version}`
   - a worktree's Odoo version → inferred from `odoo/odoo/release.py`
   - linked worktree + its source → inferred from the symlinked `odoo/` target
   - active custom addons → inferred from the worktree filesystem
   - assigned ports → `.run/{worktree}/{db}/ports`
 - the only genuine configuration is the Odoo server configuration itself, which
   is stored in a single `odoo.conf` using Odoo's own format
 - `odoo.conf` lives at Odoo's standard location `~/.config/odoo/odoo.conf`; the
   CLI always passes it explicitly (`-c ~/.config/odoo/odoo.conf`) when invoking
   odoo-bin, so CLI behavior never depends on odoo-bin's rcfile resolution
   (`~/.odoorc`, `ODOO_RC`, distro defaults)
 - the standard location is kept (rather than a workspace-local file) so manual
   `odoo-bin` runs share the same base configuration (the CLI stays a thin
   wrapper over odoo-bin); the full runtime command additionally includes
   CLI-computed values (addons path, database, ports) — `odoo where` shows the
   exact command to reproduce a CLI run manually
 - `odoo init` warns when `~/.odoorc` exists or `ODOO_RC` is set, because manual
   odoo-bin runs would resolve those instead of the shared `odoo.conf`
 - `odoo init` creates this file with good defaults (dev mode, demo data, log
   level) only when it does not exist; an existing file is never modified —
   init reports expected keys that are missing and suggests `odoo config set`
 - the postgres connection keys (`db_host`, `db_port`, `db_user`,
   `db_password`) are not written by default: absent already means "local
   defaults", and odoo-bin warns on every run about non-boolean options
   holding the literal string `False`. They are added by `odoo config set`
   (or init's port detection) when a non-default connection is needed
 - `odoo config set` preserves unknown keys but rewrites the file with
   `configparser`: comments and formatting are not preserved (accepted v1
   limitation, stated plainly in the command help)
 - consequence: this file is user-global, not workspace-scoped — it is shared by
   manual `odoo-bin` runs and (for now) across workspaces. For v1's single-active
   -workspace assumption this is acceptable.
 - `odoo.conf` holds only workspace-shared, user-editable settings:
   - postgres connection (`db_host`, `db_port`, `db_user`, `db_password`)
   - `dev_mode`, `without_demo`, `log_level`
 - per-instance values are NOT written to `odoo.conf`; the CLI computes them and
   passes them as CLI args, which override the conf file:
   - `addons_path` (per worktree, auto-discovered)
   - `-d {worktree}` (per worktree+db)
   - allocated `http_port` / `gevent_port` (per worktree+db)
   - `data_dir` is NOT passed in v1 — odoo-bin uses its default location, shared
     by all dbs/servers; per-instance `--data-dir` → `.data/{worktree}/{db}` is v2
 - resulting override chain: `odoo.conf` (base) → environment variables → CLI args
 - because the running configuration is `odoo.conf` plus computed args,
   `odoo where` is the canonical way to see the fully resolved config

## Decision record: why odoo.conf, and why at the standard location

This was the most debated decision in the design; the rationale is recorded so
the rules above are not mistaken for arbitrary choices.

**The original draft** had a `workspace.toml` at the workspace root replacing
`odoo.conf` entirely: the CLI would own all configuration and pass everything
to odoo-bin as CLI args, bypassing `odoo.conf`.

**The CTO rejected it**: CLI commands should be thin wrappers over odoo-bin, so
that people who use odoo-bin directly get the same behavior. Hence `odoo.conf`
came back, in Odoo's own format, at Odoo's standard location.

**Why that is right** (beyond the stated reason): the CLI must not invent a
second configuration language for Odoo. Owning config in a CLI format means
enumerating, translating, and documenting every Odoo setting the CLI exposes,
and chasing that mapping across Odoo versions forever. Using `odoo.conf`
verbatim makes `odoo config set` a dumb ini editor with zero translation layer.
It also preserves the escape hatch that adoption depends on: stop using the CLI
tomorrow and nothing breaks, and when something misbehaves, dropping down to
bare odoo-bin shares the same config instead of hitting a parallel universe.

**Two refinements from review:**

- relying on odoo-bin's rcfile auto-resolution is fragile (`~/.odoorc` and
  `ODOO_RC` silently take precedence), so the CLI always passes `-c`
  explicitly. The thin-wrapper claim is kept precise: manual runs share the
  same *base* config, not the CLI-computed instance identity (addons path, db,
  ports) — `odoo where` reproduces the full command.
- a workspace-local `odoo.conf` was considered (it would restore "everything
  inside `~/odoo`" and make multi-workspace via `ODOO_DIR` correct), and
  rejected to keep manual odoo-bin runs sharing the config. Because `-c` is
  explicit, the *location* is cheap to revisit later; the *format* decision is
  the durable one.

**The distilled decision rule** (applies to future debates of this kind): the
CLI does not own state that odoo-bin could own (configuration); it freely owns
state that odoo-bin cannot own (instance identity: worktrees, venvs, db-name
conventions, port allocation).

**End state**: the convention-migration plan (`requirements_v3.md`) has
odoo-bin itself adopting these conventions and owning initial `odoo.conf`
creation, at which point explicit `-c` becomes unnecessary on those versions —
`-c` is the v1 defense, not the destination.

## Use click for python cli arg parsing framework
 - upstream distributions vendor click so the bash installer only needs a Python
   interpreter; Debian/Ubuntu packages may unvendor it and depend on
   `python3-click`

## The `odoo` command is a standalone CLI tool
 - source can live in the odoo repo for review, but distributed independently
 - installed globally via uv/apt, not tied to a specific odoo version
 - manages worktrees across multiple odoo versions simultaneously

## Architecture
 - implementation should separate core operations from frontends
 - the CLI is the first frontend, but the same core should be usable by future MCP/Odoo.sh/cloud integrations
 - v1 implements the local development backend; cloud backends can be added later without changing the command model
 - the formal backend interface is deferred to v3; v1 keeps only an injectable
   process-runner seam (see `architecture.md`)
 - dependency direction: frontends depend on core, backends implement core interfaces; core does not depend on frontend code
 - advanced workflows can be provided as extensions that expose CLI commands and/or MCP tools while reusing the same core and backend APIs
 - extensions should not redefine workspace resolution, target resolution, addons path resolution, venv rules, or server lifecycle

```text
        +------------------+       +-----------------------------+
        | CLI frontend    |       | MCP frontend                |
        | odoo ...        |       | odoo-mcp / odoo mcp serve  |
        +---------+--------+       +--------------+--------------+
                  ^                              ^
                  |                              |
        +---------+------------------------------+---------+
        | Extensions                                      |
        | support workflows, Odoo.sh workflows, dump/     |
        | restore/neutralize, upgrade, scaffold, export   |
        +-------------------------+------------------------+
                                  |
                                  v
              +--------------------------------------+
              | odoo-cli core library                |
              | workspace, target, config, addons,   |
              | repos, venv, db, server, logs, rpc   |
              +------------------+-------------------+
                                 |
                     +-----------+-----------+
                     |                       |
          +----------v--------+        +-----v--------------+
          | Local backend     |        | Cloud backend      |
          | filesystem        |        | future: Odoo.sh /  |
          | worktrees, local  |        | managed workspaces,|
          | PostgreSQL,       |        | managed databases, |
          | venvs, odoo-bin   |        | cloud runners      |
          +-------------------+        +--------------------+
```

## Commands have minimal verbosity by default, default to --log-level=WARN

## Installed apps come from the database, not from config
 - there is no `install_modules` list anywhere; the set of installed modules is
   read from the database when needed (it is the source of truth)
 - `odoo init` installs no module; the initial database is created empty (base only)
 - modules are installed on demand with `odoo module install <module>`, which
   delegates to `odoo-bin module install` when the target version has it and
   polyfills it with the legacy invocation otherwise
 - `odoo db reset` reads the currently installed modules from the database,
   drops/recreates it, and reinstalls that same set; a freshly created database
   that never had modules stays empty
 - `odoo test installed` reads the installed module list from the database
 - normal server start/restart never installs modules
 - `odoo start` checks at startup whether any non-base module is installed and,
   if none is, prints a hint pointing to `odoo module install`

## Addons paths auto-discovered from worktree root
 - active custom addons are inferred from the worktree filesystem layout; there is no `addons = [...]` list anywhere
 - addons paths are resolved deterministically in this order:
   - `odoo/addons`
   - `themes` if present in the worktree
   - `enterprise` if present in the worktree
   - custom addon paths, sorted alphabetically by path
 - if any custom directory at the worktree root contains a `__manifest__.py` at its root, the worktree root is added as a custom addons path so Odoo can discover those single-addon directories
 - any custom directory at the worktree root containing one or more direct children with `__manifest__.py` is treated as a multi-addon repository and that directory is added
 - custom addon discovery ignores hidden directories and known non-addon repos such as `documentation` and `upgrade`
 - duplicate module names across addons paths are left to odoo-bin's own
   resolution rules and warnings; the CLI adds no detection of its own
 - the resolved `addons_path` is computed from the layout and passed as a CLI arg;
   it is never written to `odoo.conf`

## Database names managed by convention
 - default db name is the worktree name: `{worktree}`
 - override with `--db` flag when needed (e.g. customer databases)
 - no need to pass db name in most commands
 - commands that need an initialized database ensure it first: a missing target
   database is created and initialized empty (no modules) before the command
   proceeds — so `odoo module install crm` works right after `odoo init`
 - existence alone is not initialization: a database left empty by an
   interrupted first start (created, but odoo-bin's base install never
   finished) is detected and initialized the same way on the next command

## PostgreSQL credentials
 - PostgreSQL connection settings are workspace-level, not per database
 - they come from `odoo.conf` (`db_host`, `db_port`, `db_user`, `db_password`)
 - odoo-bin reads `odoo.conf` directly, so the CLI does not pass the password on
   the command line when launching the server
 - for the CLI's own PostgreSQL use (`db reset`, `db query`, `db shell`), read
   `db_password` from `odoo.conf` and pass it via the `PGPASSWORD` environment
   variable, not on the command line
 - individual Odoo databases do not have separate PostgreSQL passwords managed by the CLI
 - commands should not print the PostgreSQL password or include it in saved restart args

## Odoo application credentials
 - v1 does not manage Odoo login credentials and ships no command that needs them
 - when `odoo rpc` lands in v2 it will initially assume the development default
   `admin` / `admin` unless configurable credentials land at the same time
 - configurable Odoo login credentials are a v2 feature (see `requirements_v2.md`),
   likely stored in `odoo.conf`

## Secret handling
 - the only secret in v1 is the PostgreSQL password, stored in `odoo.conf` in
   plaintext (Odoo's own format); the CLI does not maintain a separate secret store
 - secrets are redacted by default in CLI output: `odoo config list`, `odoo info`,
   `odoo status`, logs, and saved restart args
 - `odoo config get db_password` and `odoo config list --reveal` may show the
   value for automation and agents
 - environment variables can override secret values
 - future: optional OS keychain / secret-store support

## Port management
 - default: http=8069, webrtc=8072
 - the `ports` file exists to keep port selection stable across restarts of the
   same `(worktree, db)`; it is created on first start and only rewritten on an
   explicit `odoo start --new-port` — ports are never reassigned silently
 - if the stored port is taken at start, refuse to start with a diagnostic:
   probe the port — if it answers like an Odoo server, report that a server is
   (probably) already running for this instance and at which URL; otherwise
   name the occupying process and suggest `--new-port`
 - `odoo start --new-port` explicitly reallocates, overwrites the `ports` file,
   and starts
 - allocation picks the smallest available port ≥ the base port that is neither
   in use nor reserved by any existing `ports` file — smallest-first reclaims
   ports freed by removed worktrees instead of growing forever
 - http and gevent reservations share a single pool: an instance's `ports` file
   reserves both its ports, and allocation for either kind skips any port
   reserved or in use for any purpose — the defaults are only 3 apart, so the
   http range must never walk onto a gevent port
 - `ports` files under `.run/` whose worktree no longer exists on disk do not
   count as reservations (presence of the worktree is the truth)
 - availability is verified by binding, never by trusting the file; the `ports`
   file is written before the final bind check so concurrent `odoo start`
   invocations see each other's reservations
 - reservation writes are atomic (temp file + rename); when the final bind
   fails, a newly created reservation is rolled back, while a pre-existing one
   is left unchanged
 - assigned ports stored in `.run/{worktree}/{db}/` so other commands can discover them
 - the default starting port can be changed in `odoo.conf` (`http_port` / `gevent_port`);
   the CLI still auto-allocates from there per `(worktree, db)` and passes the
   chosen ports as CLI args

## Persistent data management
 - v1: persistent Odoo data lives in odoo-bin's default `data_dir`; the CLI does
   not pass `--data-dir`. This means all databases and servers share one data
   directory (filestore is still namespaced per database name inside it). Not
   isolated, but acceptable for internal testing.
 - v1 `.run/{worktree}/{db}/` only contains the `ports` file
 - v2: persistent data moves to a per-instance `.data/{worktree}/{db}/` passed as
   `--data-dir`, and `.run/` gains pid/log/socket/args with the server lifecycle
 - filestore is never treated as disposable runtime state

## Server interaction
 - commands should not require the Odoo server unless inherently server-based (e.g. `odoo rpc`)
 - `odoo update` and `odoo db reset` can run whether the server is running or not
 - `odoo update` and `odoo db reset` do not stop the server; a running server may log errors or reload while the database changes
 - commands only stop or restart a running server when explicitly requested (`odoo stop`, `odoo restart`, worktree removal)

## Multitasking is handled with worktrees
 - worktrees are git worktrees from the shared bare repos in .repositories/
 - full worktrees contain real git worktrees for standard Odoo repositories
 - linked worktrees symlink standard Odoo repositories from another existing worktree and contain real checkouts only for their attached addon repositories
 - a worktree is linked when its `odoo/` is a symlink; the symlink target identifies
   the source worktree (the former `linked_from`). Nothing is stored in config.
 - linked worktrees are useful when a user needs several isolated custom-addon contexts on the same standard Odoo version without duplicating the Odoo source tree
 - commands that mutate shared source repositories should report when the current worktree is linked and make clear that the source is shared with another worktree
 - the filesystem is the authoritative list of worktrees: a worktree is a top-level
   directory in the workspace that contains an `odoo/` entry (directory or symlink);
   its kind (full vs linked) and version are derived from its contents
 - other top-level directories (e.g. a `dumps/` folder the user created) are
   ignored; v2 `odoo doctor` flags them
 - one worktree can run multiple servers, each with a different database
 - the worktree directory name is the worktree id
 - worktree names may contain only ASCII letters, digits, `_`, `-`, and `.`,
   and must start with a letter, digit, or `_` (names become argv positionals
   for tools like `createdb` and must never look like command-line options)
 - worktree names cannot be empty, contain path separators, or collide with internal workspace directories (`.repositories`, `.venvs`, `.run`, `.data`)

## Target flags
 - `-w` / `--worktree` — specify which worktree to target
 - `-d` / `--db` — specify which database to target (defaults to `{worktree}`)
 - both are optional on all commands — omit to infer from context

## Target resolution order
 - worktree: cwd if inside a worktree → `-d` hint → only worktree if there's
   exactly one → error
 - cwd detection uses the logical path (`$PWD`, validated against `getcwd()`):
   inside a linked worktree's symlinked `odoo/`, the physical path points at the
   source worktree, but the command must target the linked worktree
 - `-d` hint: when several worktrees exist and the cwd does not decide, the
   database selects the worktree if unambiguous:
   - a worktree named like the database wins (every worktree's default db is
     its own name, so `odoo start -d 19.0` targets worktree `19.0`); this
     beats run state because the naming convention is stable while run state
     accumulates
   - else the single worktree holding run state for that database
     (`.run/{worktree}/{db}/ports`), so `odoo start -d customer-a` works from
     anywhere once that database ran somewhere
   - several worktrees with run state for the database → explicit ambiguity
     error listing them
 - database: explicit `--db` → default `{worktree}`
 - if worktree resolution fails because multiple worktrees exist, print an explicit error:
   - explain that no default worktree is configured
   - list available worktrees
   - tell the user to run the command from inside a worktree or pass `--worktree`

## Use cases
 - **Code developer**: one db per worktree, db name derived automatically.
   `odoo start` from within `~/odoo/my-feature/` just works.
 - **Customer support**: multiple dbs per version, explicit db names.
   `odoo start -d customer-a` from within `~/odoo/19.0/`.
 - **Customer support with custom addons**: linked worktree with isolated addon repos and shared Odoo source.
   `odoo worktree create customer-a 19.0 --linked --addon customer-a-addons`

## Phases

v1 is deliberately scoped down for internal testing: the minimal edit → run →
test loop, foreground server only, no process lifecycle management. Linked
worktrees and `odoo repo add` are in v1 because support users are among the v1
testers and linked worktrees are the hardest resolution case to validate early.

- **v1**: init, config (`get`/`set`/`list`, no wizard), repo (add/enable),
  worktree create (full and linked), venv, start (foreground only), where,
  module install, update, test, db reset, shell
- **v2**: everything deferred from v1 — server lifecycle (stop, restart,
  `start --background`), the `config` wizard, `venv --apt`, info, status,
  doctor, pull, log, rpc, db shell, db query, worktree list/remove — plus support
  workflows: dump/restore/neutralize, checkout, scaffold
- **v3**: Platform — MCP frontend, cloud backend, extensions — see
  `requirements_v3.md`

In v1, `.run/{worktree}/{db}/` holds only the `ports` file (the foreground
server logs to the terminal); pid/socket/args and background logs arrive with the
v2 server lifecycle.

## Available commands

### `odoo init` [v1]
 - bootstrap the workspace: clone repos, create initial worktree, set up venv
 - minimal, good defaults, fully unattended — no questions asked
 - `odoo init 19.0` — create initial worktree `19.0` on version `19.0`
 - with no version argument, defaults to the latest stable version: the highest
   `N.0` branch present in the freshly cloned odoo.git (no hardcoded version
   list, no extra network round-trip)
 - clones odoo.git and documentation.git by default (enterprise, themes, upgrade via `odoo repo enable`)
 - clones are bare and blobless (`git clone --bare --filter=blob:none`): full
   commit/tree history so `git log` and `git blame` work, blobs fetched on demand
   by checkouts; `--full` opts into complete clones
 - consequence of blobless: first-time `git blame` and checkouts of new refs need
   network access; git failures in that situation should mention that the
   repository is partial/blobless
 - installs no module; the initial database is created empty (use `odoo module install` afterwards)
 - writes the default `odoo.conf` at `~/.config/odoo/odoo.conf`
 - demo data enabled by default (override with `--no-demo-data` or `without_demo` in `odoo.conf`)
 - on completion: prints clear next steps for the created worktree (`cd ~/odoo/{worktree} && odoo start`)
 - re-running `odoo init` converges: corrupt partial clones (no resolvable
   HEAD) are replaced, an incomplete worktree is repaired, a valid one is
   completed; fetch failures on already-present repos only warn, so offline
   re-runs still work
 - postgres: check if installed, installing it first when `psql` is missing
   - Debian/Ubuntu/WSL: use `apt-get update` and `apt-get install -y postgresql`
   - macOS: use `brew install postgresql`
   - after installation, best-effort start the service (`systemctl`/`service`
     on Linux, `brew services` on macOS); warn if the service cannot be started
     automatically
   - if no supported package manager is found, print install instructions for
     the platform and exit
   - if installed but connection fails: tell user to fix the `db_*` keys with
     `odoo config set`
   - before warning, when `db_host`/`db_port` are unset, look for local servers
     on non-standard ports (`.s.PGSQL.<port>` socket files, `pg_lsclusters`);
     if exactly one answers, save its port as `db_port`; if several answer,
     list them in the warning
 - wkhtmltopdf (odoo-bin's default PDF engine): check if installed, installing
   it when the binary is missing — best-effort, unlike postgres: any failure
   warns and init continues (a workspace without a PDF engine still runs;
   reports and their tests fail until it is installed)
   - Debian/Ubuntu/WSL: `apt-get install -y wkhtmltopdf`
   - macOS: the project is discontinued and gone from Homebrew, so download
     the last official .pkg (0.12.6-2, x86_64) from the wkhtmltopdf/packaging
     GitHub releases and run `installer` with sudo; on Apple Silicon the
     binary needs Rosetta 2 — when it does not run after install, warn with
     the `softwareupdate --install-rosetta` command
 - cairo + pkg-config (barcode/QR rendering through reportlab): same
   best-effort check and install (`brew install cairo pkg-config` on macOS,
   `apt-get install -y libcairo2-dev pkg-config` on Debian/Ubuntu); with
   cairo present, venv creation adds the `rlPyCairo` backend

### `odoo config` [v1]
Non-interactive workspace configuration: a thin, scriptable front over the shared
`odoo.conf`. No interactive wizard in v1 (the wizard is a v2 addition); `odoo init`
writes good defaults and the user edits from there.

Subcommands:
 - `odoo config list [--json] [--reveal]` — print resolved config (`odoo.conf`
   values plus which optional repos are enabled), secrets redacted unless `--reveal`
 - `odoo config get $KEY` — print one value
 - `odoo config set $KEY $VALUE` — set one `odoo.conf` value; pure edit, no side effects

Keys:
 - keys are `odoo.conf`'s own flat ini keys, e.g. `db_host`, `db_port`,
   `db_user`, `db_password`, `dev_mode`, `without_demo`, `log_level`
 - there are no dotted paths and no `repositories.*` keys; enabling repos is a
   `repo` verb (`odoo repo enable`), not a config key, because it clones and
   touches worktrees

The interactive `odoo config` wizard (bare command that walks postgres
connection, enterprise, dev mode, etc.) is deferred to v2 — see
`requirements_v2.md`; for enterprise it delegates to `odoo repo enable`.

### `odoo repo enable $REPO [$URL]` [v1]
 - enable a built-in optional repo (`enterprise`, `themes`, `upgrade`); side-effecting
 - clones/fetches the repo into `.repositories/` (e.g. `.repositories/enterprise.git`)
 - fetching updates origin branches only and never deletes local-only branches
   (worktree feature branches); branches checked out in worktrees are left to
   their worktrees (fast-forwarding them is v2 `odoo pull` territory)
 - newly enabled optional repos are automatically available to future worktrees
 - default: adds the repo to all compatible existing worktrees
 - `--future-only` — clone/fetch only; leave existing worktrees untouched
 - `--to $WORKTREE` (repeatable) — add only to the listed worktrees
 - if the repo lacks a worktree's detected version, skip that worktree and warn
 - linked worktrees are skipped with a warning pointing at their source
   worktree (standard repos are symlinks created at worktree-creation time, so
   an existing linked worktree does not gain the repo automatically even after
   its source has it — open point, see `requirements_v3.md` → "Open questions")
 - always prints a summary: repo cloned/fetched, worktrees updated, worktrees
   skipped with the reason
 - `enterprise` defaults to git URL `git@github.com:odoo/enterprise.git`
   - relies on the user's existing SSH/git setup, does not manage SSH keys
   - also accepts HTTPS URLs (token-based auth or private mirrors)
   - supports local paths for users who already have the repo elsewhere
 - no `disable` verb in v1 (removing a cloned repo is destructive; punt)

### `odoo repo add` [v1]
 - register and clone/fetch an additional git repository into `.repositories/`
 - `odoo repo add customer-a-addons git@github.com:customer/customer-a-addons.git`
 - `odoo repo add support-tools git@github.com:odoo/support-tools.git`
 - repositories are stored in the same flat namespace as standard repositories, e.g. `.repositories/customer-a-addons.git`
 - adding a repository does not modify existing worktrees
 - a registered repository only affects a worktree when it is checked out into that worktree, for example through `odoo worktree create --addon`
 - repository names follow the same character rules as worktree names and cannot collide with built-in repository names unless the command is explicitly configuring that built-in repository
 - a repository may exist in `.repositories/` without an `origin` remote
   (manual/local setups); it surfaces with no URL, and commands that need to
   fetch it fail with a clear error
 - no local paths for this command in v1

### `odoo worktree create` [v1]
 - create a new worktree (git worktrees from .repositories/)
 - one positional argument means name = version: `odoo worktree create 19.0`
   creates worktree `19.0` on version `19.0`; valid only when the argument
   resolves to an Odoo ref/version (`19.0`, `master`, `saas-19.4`)
 - two positional arguments mean explicit name + version: `odoo worktree create
   my-feature 19.0` creates worktree `my-feature` on version `19.0`
 - `odoo worktree create my-feature` is invalid because `my-feature` does not
   resolve to an Odoo ref/version
 - the version argument is used to choose the initial checkout; it is not persisted (the source is the truth)
 - re-running `odoo worktree create` converges: the leftover of an interrupted
   creation is repaired, and an existing valid worktree of the same kind and
   version is completed (missing standard checkouts, symlinks, and `--addon`
   checkouts are added; present ones are never touched)
 - includes odoo.git plus any optional repos currently present in `.repositories/` (e.g. `enterprise.git`, `themes.git`)
 - if odoo.git does not have the requested version, fail
 - if an optional repository does not have the requested version, skip that repository and report a warning
 - sets up venv if needed (reuses existing .venvs/{version} if available)
 - checkout branch convention (branch-per-worktree): git allows a branch to be
   checked out in only one worktree per repository, and all worktrees share the
   bare repos in `.repositories/`, so two worktrees on the same version cannot
   both sit on the version branch. Therefore:
   - when name = version (`odoo worktree create 19.0`), the worktree checks out
     the version branch itself
   - when name ≠ version (`odoo worktree create fix-pos-flow 19.0`), a new
     local branch named after the worktree is created from the version
     (`git worktree add -b fix-pos-flow … 19.0`) in every repo checked out into
     the worktree — feature worktrees start on a branch ready to push to the
     dev remote, matching the convention of identical branch names across
     odoo/enterprise
   - a pre-existing branch with the worktree's name (left over from a removed
     worktree of the same name) is reused, never reset
   - consequence: the branch is created in every repo of the worktree, even
     ones that will never be touched (e.g. `documentation`)
   - the worktree's version remains derived from `odoo/odoo/release.py`, never
     from the branch name

### `odoo worktree create --linked` [v1]
 - `odoo worktree create customer-a 19.0 --linked --addon customer-a-addons --addon support-tools`
 - creates a linked worktree for custom addon work on an existing Odoo source tree
 - the SOURCE argument is the unified "what this worktree starts from" slot:
   a version/ref for a full worktree, an existing worktree's name with
   `--linked`; both readings coincide for version-named worktrees
 - with `--linked`, SOURCE must name an existing full worktree
   - the linked worktree's version is the source's detected Odoo version
   - a linked worktree is rejected as source (symlink chains break silently
     when the middle worktree is removed); the error hints at the real source
   - standard source repositories (`odoo`, `documentation`, and enabled standard repositories such as `enterprise` and `themes`) are symlinked from the source worktree
   - attached addon repositories are checked out as real git worktrees at the linked worktree root
 - SOURCE naming a worktree *without* `--linked` duplicates it [v1]:
   - every repo the source has (addons included) is checked out on a branch
     named after the new worktree, starting from the source repo's current
     branch (HEAD commit when detached)
   - duplication preserves the worktree's nature: duplicating a linked
     worktree yields another linked worktree on the same original (never a
     symlink chain), with the source's addon checkouts duplicated
   - source checkouts without a backing repository in `.repositories/` are
     reported as skipped; non-repo directories (dumps, notes) are ignored
   - a worktree source wins over a ref of the same name; the readings
     coincide for version-named worktrees (their branches are named after
     the version)
 - when SOURCE is an existing worktree (duplicate or `--linked`), the new
   worktree's database is created from the source's as a template
   (`createdb -T`, filestore included), sparing a reinstall of the source's
   module set; `--empty-db` opts out
   - best-effort: when the source database is missing, uninitialized, or
     postgres is unreachable, creation proceeds and the empty-on-first-start
     rule applies as before; the target database is never overwritten
 - `--addon $REPOSITORY` may be passed multiple times
 - `--addon` only accepts repository names that are present in `.repositories/` (e.g. cloned through `odoo repo add`)
 - `--addon` is a creation-time checkout action; addon membership is thereafter determined by the directories present at the worktree root, not by any stored list
 - addon repositories are checked out as siblings of `odoo` and `enterprise`
 - after creation, addon membership is determined by the directories present at the worktree root
 - addon repositories branch from the Odoo-version branch when it exists; otherwise from the repository's default branch, with a warning
 - addon checkouts follow the same branch-per-worktree convention as full worktrees: the checked-out branch is named after the worktree, created from that base branch (so the same addon repo can be attached to several linked worktrees)

### `odoo worktree list` [v2]
 - list all worktrees with their version, branch, and running server status

### `odoo worktree remove $NAME` [v2]
 - stops any running servers for the worktree
 - cleans up `.run/` state for the worktree
 - leaves `.data/` persistent database data untouched by default
 - deleting `.data/` requires an explicit flag or confirmation
 - removes the git worktree

### `odoo venv` [v1]
 - create/recreate the venv for the current version (kept in v1 for debugging)
 - resolves to `.venvs/{version}` for the worktree's detected version
 - `--apt` (install deps system-wide with apt) is deferred to v2

### `odoo start` [v1]
 - `odoo start` — starts the server in the current terminal (foreground only in v1)
 - on first start for a database, creates/initializes an empty database (no modules)
 - at startup, if no non-base module is installed, prints a hint pointing to `odoo module install`
 - `odoo start -d customer-a` — start with a specific database
 - dev mode (auto-reload) enabled by default, override with `--prod` or `dev_mode` in `odoo.conf`
 - ensures the resolved venv exists before starting, creating it on demand
   (see "Venv strategy"; the same rule applies to every command that runs odoo-bin)
 - allocates a free port and writes it to `.run/{worktree}/{db}/ports`; the server
   logs to the terminal
 - if the stored port is already taken, refuses to start with a diagnostic
   (see "Port management"); `--new-port` explicitly reallocates
 - stop with Ctrl-C — there is no `odoo stop`/`odoo restart` in v1
 - background mode (`--background`), `odoo stop`, and `odoo restart` (with
   `.run/.../args`) are deferred to v2 — see `requirements_v2.md`

### `odoo where` [v1]
 - show exactly what the CLI inferred for the current command context
 - workspace root, worktree, database, venv, addons paths, resolved `odoo.conf` path
 - sanitized `odoo-bin` command args for debugging and copy/paste
 - `--json` for machine-readable output

### `odoo info` [v2]
 - overview of the current setup: server port, credentials, branch statuses, etc.

### `odoo status` [v2]
 - short daily glance at the current target
 - shows current worktree, database, server status, URL, ports, version/branch, dirty repos
 - includes a concise next useful action when obvious

### `odoo pull` [v2]
 - pulls latest changes across the repos

### `odoo test $MODULE [-t $TAG]` [v1]
 - recreates the test db (database and filestore) from scratch on every run;
   `--keep-db` reuses the existing one instead (faster reruns)
 - the test db is named `{database}-test` (default: `{worktree}-test`);
   derived by convention, never stored
 - rationale for fresh-by-default: at_install tests run per module during
   loading, with a registry of only the modules loaded so far — a test db
   carrying the schema of a previous run breaks them (inserts hit NOT NULL
   columns of not-yet-loaded modules)
 - with `--keep-db`, modules already installed in the test db are passed to
   odoo-bin with `-u` (their tests run again) and only missing ones with
   `-i`: odoo-bin runs tests solely for modules installed/updated in the
   current process, so `-i` alone on a reused test db would run zero tests
 - only outputs final test results by default
 - `$MODULE`: module name, `installed` (modules installed in the database), or `all` (every addon)
 - `-t test_foo` resolves to the correct odoo test tag format automatically
 - tours: TBD (requires running server + browser, likely a separate `odoo test-tour`)

### `odoo log` [v2]
 - (v1 logs to the terminal in foreground; this command arrives with the v2 lifecycle)
 - logs are always written to `.run/{worktree}/{db}/log` as plain text
 - `odoo log` — show recent logs
 - `odoo log --follow` — tail logs in real time
 - `odoo log --date 2026-06-04` — show logs from a specific date
 - `odoo log --search "error"` — search/filter logs
 - future: structured jsonl format with `--format jsonl`

### `odoo shell [-c $CODE]` [v1]
 - opens an interactive python shell, or executes code and returns the output

### `odoo rpc $PATH [$JSON]` [v2]
 - executes an rpc call to the current server (new path-based API)
 - `odoo rpc /res.partner/search_read '{"domain": [], "fields": ["name"], "limit": 5}'`
 - JSON payload as second arg, or from stdin for larger payloads
 - output: JSON to stdout (pipeable to jq, parseable by agents)

### `odoo module install $MODULE` [v1]
 - install one or more modules into the current database
 - delegates to `odoo-bin module install` when the target Odoo version provides
   it; otherwise `OdooBinService` polyfills it with the legacy invocation
   (`-i` + `--stop-after-init`)
 - ensures the database exists first (see "Database names managed by convention")
 - this is the only way modules get installed; there is no configured module list
 - `odoo module install crm` — install CRM into the current database

### `odoo update [modules]` [v1]
 - update modules in the database (default: all installed)

### `odoo db reset` [v1]
 - reads the currently installed modules from the database
 - drops and recreates the db, then reinstalls that same set of modules
 - a database that never had modules is recreated empty

### `odoo db shell` [v2]
 - opens a psql shell in the current db

### `odoo db query [--csv] $SQL` [v2]
 - runs sql command in the current db, outputs the result

## Open points
 - `odoo db reset` and `.data/` lifecycle
   - v1: `odoo db reset` acts only on the PostgreSQL database (drop/recreate);
     it does not touch the shared default data_dir / filestore
   - v2: once data is isolated per `(worktree, db)` under `.data/`, decide whether
     reset should also clear that database's filestore/data directory

## Future commands (to be designed)
 - `odoo doctor` [v2] — diagnose broken or incomplete setups
   - should be designed to provide genuinely helpful, actionable diagnostics
   - avoid being only a shallow checklist of installed tools
 - `odoo pull` / `odoo fetch` [v2] — sync repositories with remotes
   - design agreed in `requirements_v2.md` → "`odoo fetch` and `odoo pull`":
     `fetch` updates the bare repos; `pull` fast-forwards a worktree's checkouts
     (ff-only, skip+guide on divergence/dirty/feature branches); venv drift is
     `odoo start`'s job; "morning sync" (`--all`) and offline pull are deferred
 - `odoo dump / restore / neutralize` [v2] — database lifecycle for support workflows
 - `odoo checkout` [v2] — clarify how branch switching should work in a worktree-first model
   - distinguish switching a worktree version from creating/using feature branches
   - define behavior when a branch exists in some repos but not others
 - `odoo scaffold` [v2] — generate a new module skeleton

The v3 platform phase (MCP frontend, cloud backend, extensions) is tracked in
`requirements_v3.md`.
