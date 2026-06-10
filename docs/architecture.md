# Odoo CLI architecture

This document describes the target implementation structure for `odoo-cli`.
It is the bridge between `requirements.md`, `usecase.md`, and the code we want
to write.

The main design goal is to keep the CLI pleasant and predictable while making
the core operations reusable by future frontends such as MCP or Odoo.sh tooling.

`requirements.md` and `usecase.md` are the canonical inputs for this document.
The current implementation is not a compatibility constraint and can be replaced
when the new architecture is implemented.

## Dependency policy

Runtime Python dependencies should be limited to:

- Python standard library
- vendored `click`

Runtime target:

- Debian 12 Bookworm or newer
- Python 3.11 or newer

Reasons:

- Debian 12 provides Python 3.11, with the standard-library `configparser` we
  use to read/write `odoo.conf`
- bash installers should only need to find a supported Python interpreter, not
  manage Python package installation
- `click` gives the CLI useful command ergonomics, validation, shell completion,
  and help rendering
- `click` is small enough to vendor in upstream source distributions
- Debian/Ubuntu packaging can unvendor `click` and depend on the standard
  `python3-click` package
- keeping the core dependency-free makes future embedding easier

Consequences:

- no Typer
- no Rich
- no questionary
- no pydantic/dataclass serializers
- no TOML/config writer dependency (use stdlib `configparser` for `odoo.conf`)
- no runtime dependency installation step for the upstream bash installer

Vendoring policy:

- upstream source distributions include `click` under `odoo_cli/_vendor`
- imports go through one small CLI-layer compatibility module so distribution
  packages can switch to system `click` without touching command code
- vendored dependency licenses are kept with the vendored source

`click` should only be imported by the CLI frontend layer. Core modules must not
import `click`; they should raise typed exceptions and return structured result
objects.

Config file reading/writing:

- the only config file is the shared `odoo.conf` at `~/.config/odoo/odoo.conf`,
  in Odoo's own ini format
- read and write it with the standard-library `configparser`
- there is no `workspace.toml` and no TOML writer
- preserving user comments is not a v1 requirement

Testing:

- prefer `unittest`, `tempfile`, and `unittest.mock`
- avoid test-only framework dependencies unless they are explicitly justified

## Architectural layers

```text
odoo_cli/
    cli/                 click frontend and terminal rendering
    commands/            thin command adapters
    core/                frontend-independent domain logic
    backends/            local/cloud backend implementations
    util/                small stdlib helpers
    mcp/                 future MCP frontend
    extensions/          future advanced workflows
```

Dependency direction:

```text
cli.main -> commands

commands -> cli.context / cli.output / cli.prompts
commands -> core services

core services -> backend interface
core services -> util

backends.local -> backend interface
backends.local -> util

mcp -> core services
extensions -> core services
```

Rules:

- `core` does not import `click`
- `core` does not print
- `core` does not read stdin
- `core` does not call `sys.exit`
- `commands` parse CLI arguments and call core services
- `cli` renders messages, prompts, and tables
- `backends` implement filesystem/process/database details behind core-facing interfaces
- `backends` do not import CLI modules
- future MCP tools call the same core services as CLI commands

## Proposed package layout

```text
odoo_cli/
    __init__.py

    cli/
        __init__.py
        main.py              # click group registration
        context.py           # CLI context object and option normalization
        output.py            # plain/text/json output helpers
        prompts.py           # click.prompt/click.confirm wrappers

    commands/
        __init__.py
        init.py
        config.py            # bare wizard + get/set/list/enable
        module.py            # odoo module install
        repo.py
        worktree.py
        start.py
        db.py
        update.py
        test.py
        log.py
        shell.py
        rpc.py
        info.py
        status.py
        pull.py

    core/
        __init__.py
        errors.py
        models.py
        paths.py
        workspace.py
        odoo_conf.py         # OdooConf reader/writer (configparser)
        target.py
        repositories.py
        worktrees.py
        addons.py
        venvs.py
        modules.py           # install / read installed modules
        odoo_bin.py
        postgres.py
        database.py
        server.py
        logs.py
        rpc.py
        testing.py
        info.py
        status.py

    backends/
        __init__.py
        base.py
        local.py

    util/
        __init__.py
        process.py
        fs.py
        toml.py
        git.py
        net.py

    mcp/
        __init__.py          # future

    extensions/
        __init__.py          # future
```

The exact file names can evolve, but the boundaries should stay stable.

## Core data model

Use dataclasses for data carried across services. They are simple, typed, and
stdlib-only.

### `Workspace`

Represents a resolved workspace root.

Fields:

- `root: Path`
- `config: OdooConf`

The workspace is identified by the presence of `root / ".repositories/odoo.git"`;
there is no marker config file.

Important paths:

- `~/.config/odoo/odoo.conf` (shared config, outside the workspace)
- `workspace.root / ".repositories"`
- `workspace.root / ".venvs"`
- `workspace.root / ".run"`
- `workspace.root / ".data"`
- `workspace.root / worktree_name`

`Workspace` should not do heavy work. It is a value object with path helpers.

### `OdooConf`

Parsed `~/.config/odoo/odoo.conf` (Odoo's own ini format, read via `configparser`).

Responsibilities:

- expose the shared Odoo server settings (`db_host`, `db_port`, `db_user`,
  `db_password`, `dev_mode`, `without_demo`, `log_level`, ...)
- redact secrets for display
- support reading and writing individual keys for `odoo config get/set`

It should not:

- store the repository list (derived from `.repositories/`)
- store per-worktree overrides (there are none in v1)
- infer worktree versions
- list active addon directories
- store runtime ports, process state, or data paths

It holds only workspace-shared settings. Per-instance values (`addons_path`,
`data_dir`, `-d`, ports) are never read from or written to it; they are computed
by services and passed as CLI args that override the conf.

### `RepositorySpec`

A repository derived from the filesystem, not a registry entry.

Fields:

- `name: str` (from the `.repositories/{name}.git` directory)
- `url: str | None` (the bare repo's git `origin` remote)

Rules:

- repository names share one flat namespace
- a repository is "enabled" iff `.repositories/{name}.git` exists; `odoo` and
  `documentation` are cloned by `odoo init`
- optional builtins (`enterprise`, `themes`, `upgrade`) exist only once enabled
  via `odoo config enable`
- customer addon repositories are added by `odoo repo add`
- there is no stored enabled/disabled flag or URL; both come from disk

### `Worktree`

Filesystem worktree.

Fields:

- `name: str`
- `path: Path`
- `linked_from: str | None` (derived, not stored)

Derived facts:

- version from `path / "odoo/odoo/release.py"`
- `linked_from`: `None` for a full worktree; for a linked worktree, the source
  worktree name read from the `odoo/` symlink target (a symlinked `odoo/` is what
  makes a worktree linked)
- active standard repos from directories/symlinks present in the worktree
- active custom addons from filesystem discovery

The filesystem is the authoritative list of worktrees: every top-level directory
other than the dot-directories is one. No config entry is needed for any worktree.

### `Target`

Resolved command target.

Fields:

- `workspace: Workspace`
- `worktree: Worktree`
- `database: str`

Target resolution:

- worktree: explicit `--worktree` -> cwd inside worktree -> only worktree -> error
- database: explicit `--db` -> `odoo-{worktree}`

All command services should receive a `Target` when they operate on a worktree
or database.

### `ServerInstance`

Runtime server identity.

Fields:

- `target: Target`
- `run_dir: Path`
- `data_dir: Path | None`

Path rules:

- `run_dir = workspace.root / ".run" / worktree / database`
- v1: `data_dir` is `None` — odoo-bin uses its default location (shared by all
  dbs/servers) and the CLI passes no `--data-dir`
- v2: `data_dir = workspace.root / ".data" / worktree / database`

Ports belong to `ServerInstance`, not to a worktree.

### `RunState`

Ephemeral runtime state read from `.run/{worktree}/{db}/`.

Files:

- `pid`
- `log`
- `ports`
- `socket`
- `args`

Rules:

- runtime state can be deleted safely
- secrets are never written to `args`
- auto-assigned ports live in `ports`
- explicit fixed port requests may be stored in sanitized `args`

### `OdooBinCommand`

Structured command specification for an `odoo-bin` invocation.

Fields:

- `executable: Path`
- `argv: list[str]`
- `cwd: Path`
- `env: dict[str, str]`
- `redacted_argv: list[str]`
- `purpose: str`

Rules:

- `argv` may contain only non-secret command arguments
- secrets are passed through `env` or resolved by the child process at runtime
- `redacted_argv` is safe to display and safe to write to `.run/.../args`
- command construction lives in `OdooBinService`, not in command modules or
  individual workflow services

## Services

Services contain behavior. They should be small enough that commands can compose
them without becoming a second business layer.

### `WorkspaceResolver`

Responsibilities:

- find active workspace using the requirements resolution order (`ODOO_DIR` else `~/odoo`)
- validate the workspace by the presence of `.repositories/odoo.git`
- load the shared `odoo.conf`
- create initial workspace skeleton and write the default `odoo.conf` for `odoo init`

### `ConfigService`

Backs the `odoo config` command (bare wizard + `get`/`set`/`list`/`enable`).

Responsibilities:

- read/write the shared `~/.config/odoo/odoo.conf` via `configparser`
- get/set/list individual keys for the scriptable subcommands
- redact secrets (`db_password`) for output, with an explicit reveal path
- drive the interactive wizard (postgres connection, dev mode, demo data, ...)
- enable optional builtin repositories (delegates the clone to `RepositoryService`)

It should expose explicit methods rather than generic nested mutation.

Examples:

- `get(key)` / `set(key, value)` / `list(reveal=False)`
- `enable_repository(name, url=None, scope=...)`  # side-effecting: clone + optional worktree checkout

There are no per-worktree override methods in v1. Repository URLs are never
written here; enabling a repo is a clone, and its URL is the git remote.

### `RepositoryService`

Responsibilities:

- register repositories
- clone/fetch bare repositories under `.repositories`
- check whether a branch/version exists
- create git worktrees from registered bare repositories
- report dirty/ahead status

The service should use `util.git` for subprocess calls and should not parse CLI
arguments.

### `WorktreeService`

Responsibilities:

- create full worktrees
- create linked worktrees
- list worktrees
- remove worktrees
- validate worktree names

Full worktree creation:

- creates real git worktrees for `odoo`, `documentation`, and every optional
  standard repository present in `.repositories/`
- skips optional repositories that lack the requested version and reports a
  warning

Linked worktree creation:

- validates the `linked_from` source worktree exists
- validates requested version against source worktree detected version
- symlinks standard repositories from source worktree
- checks out addon repositories as real git worktrees at the linked worktree root
- stores nothing: the worktree is linked because its `odoo/` is a symlink, and
  the symlink target records the source

### `TargetResolver`

Responsibilities:

- resolve target worktree
- resolve database name
- produce explicit errors when ambiguous
- return a `Target`

This service is central. Commands should not implement their own target
resolution logic.

### `AddonsPathResolver`

Responsibilities:

- compute deterministic `--addons-path`
- include `odoo/addons`
- include `themes` if present
- include `enterprise` if present
- include custom addon paths discovered from the worktree root
- ignore hidden directories and known non-addon repositories such as
  `documentation` and `upgrade`

It should only read the filesystem. It should not read an `addons = [...]` list.

### `VenvService`

Responsibilities:

- detect Odoo Python requirement from `odoo/odoo/release.py`
- resolve shared venv path `.venvs/{version}` for the detected version
- create/rebuild venv
- install Odoo requirements

### `PostgresService`

Responsibilities:

- build the PostgreSQL environment from the `db_*` settings in `odoo.conf`
- check connection
- create/drop databases
- run SQL
- terminate database connections before reset

The PostgreSQL password is read from `odoo.conf` and passed through `PGPASSWORD`,
not on the command line.

### `DatabaseService`

Responsibilities:

- initialize an empty DB on first start (no modules)
- reset DB: read the currently installed modules, drop/recreate, reinstall that set
- expose `db shell` and `db query`

Installed modules are read from the database (`ir_module_module`); there is no
configured module list. Module installation itself is delegated to
`ModuleService` / `OdooBinService` (`odoo module install`).

In v1, `db reset` acts only on the PostgreSQL database (drop/recreate) and does
not touch the shared default data_dir / filestore. The per-instance `.data`
lifecycle is a v2 concern.

### `OdooBinService`

Responsibilities:

- build all `odoo-bin` command specifications
- expose high-level builders for server start, module install, module update,
  tests, shell, and other direct Odoo invocations
- rely on odoo-bin auto-loading the shared `~/.config/odoo/odoo.conf`; do NOT
  pass `-c` and do NOT duplicate `odoo.conf` values into argv
- only add the per-instance args that must override the conf: `--addons-path`,
  `-d {database}`, and the allocated `--http-port`/`--gevent-port`
- include deterministic addons paths from `AddonsPathResolver`
- v1: do NOT pass `--data-dir` (odoo-bin uses its default, shared data location);
  v2 adds per-instance `--data-dir` from `ServerInstance`
- the PostgreSQL password comes from `odoo.conf` (read by odoo-bin itself), so it
  never appears in process arguments
- apply Odoo-version-specific behavior in one place
- validate that requested CLI features are supported by the target Odoo version
- produce sanitized/restartable argv for `.run/{worktree}/{db}/args`

This service is the only owner of `odoo-bin` CLI details. Other services should
ask it for an `OdooBinCommand` and then execute that command through the backend.

Version-dependent behavior should be represented explicitly, for example with a
small capability table keyed by detected Odoo version. Examples include renamed
or removed flags, test behavior, dev-mode flags, gevent/longpolling behavior, and
module install/update invocation details.

### `ServerService`

Responsibilities:

- request server-start commands from `OdooBinService`
- allocate runtime ports per `(worktree, database)`
- start foreground/background server
- stop server
- restart using `.run/{worktree}/{db}/args`
- write/read runtime state

`ServerService` should depend on:

- `TargetResolver`
- `AddonsPathResolver`
- `VenvService`
- `PostgresService`
- `OdooBinService`
- `RunStateStore`

### `RunStateStore`

Responsibilities:

- read/write `.run/{worktree}/{db}` files
- sanitize saved args
- check stale pid files
- remove runtime state during stop/worktree removal

It should not own persistent data.

### `InfoService` and `StatusService`

Responsibilities:

- gather current target information
- report inferred workspace/worktree/database
- report server status, URL, ports, version, dirty repos
- redact secrets
- return structured data for `--json`

These should call other services rather than reimplement discovery.

### `RpcService`

Responsibilities:

- resolve current server URL from run state
- authenticate with the v1 development default `admin` / `admin` (configurable
  Odoo login credentials are a v2 feature)
- execute JSON RPC/path RPC
- return JSON-compatible data

## Backend interfaces

The backend layer keeps local filesystem/process behavior separate from future
cloud behavior.

### `Backend`

Defines operations that may differ between local and cloud environments:

- repository operations
- worktree operations
- server lifecycle
- database lifecycle
- logs
- generic command execution
- `OdooBinCommand` execution

### `LocalBackend`

Implements the current local workflow:

- filesystem under `~/odoo`
- git subprocesses
- local PostgreSQL
- local venvs
- local `odoo-bin`

Future cloud backends can implement the same core concepts without changing the
CLI grammar. They may execute an `OdooBinCommand` locally, translate it into a
remote job, or reject unsupported capabilities through typed errors.

## CLI command shape

Commands should be thin adapters.

Example pattern:

```python
@click.command()
@click.option("-w", "--worktree")
@click.option("-d", "--db")
@click.pass_obj
def status(ctx: CliContext, worktree: str | None, db: str | None) -> None:
    target = ctx.services.targets.resolve(worktree=worktree, db=db)
    result = ctx.services.status.get(target)
    ctx.output.render_status(result)
```

Command modules should not:

- construct `odoo-bin` arguments directly
- read or write `odoo.conf` directly (go through `ConfigService`)
- manually inspect `.run`
- manually infer addons paths
- call `sys.exit`

## Result and error handling

Core services should return structured results and raise typed errors.

Example error classes:

- `OdooCliError`
- `WorkspaceNotFound`
- `InvalidWorkspace`
- `TargetAmbiguous`
- `WorktreeNotFound`
- `RepositoryNotFound`
- `VersionNotFound`
- `PortUnavailable`
- `PostgresError`
- `ServerNotRunning`

CLI layer translates errors into concise messages and exit codes.

Suggested exit codes:

- `0`: success
- `1`: normal user-facing failure
- `2`: CLI usage error

## Output model

Human output:

- use `click.echo` and `click.secho`
- keep default verbosity low
- show concise next actions when helpful

Machine output:

- commands that expose state should support `--json`
- JSON should be produced from structured result objects
- secrets are redacted unless an explicit option requests them

## Testing strategy

The default test suite should be fast, deterministic, and runnable on a machine
that has only Python 3.11 and the vendored dependencies. Tests that need git,
PostgreSQL, or a real Odoo checkout should be clearly separated.

Test layout:

```text
tests/
    unit/           core services with fake backends and temp workspaces
    cli/            click command parsing, output, and error handling
    integration/    local backend behavior using local tools, no network
    e2e/            gated real-Odoo workflows
    fixtures/       small workspace/repository/addon fixtures
```

Default command:

```text
python -m unittest discover
```

### Unit tests

Unit tests should focus on service boundaries. They should not start Odoo, talk
to PostgreSQL, fetch remote repositories, or depend on the user's real
`~/odoo`.

Use:

- `tempfile.TemporaryDirectory` for isolated workspaces
- fake backend implementations for process, git, and database operations
- small fixture builders for `Workspace`, `Worktree`, `Target`, and `OdooConf`
- `unittest.mock` only at process/backends boundaries

High-value unit coverage:

- `WorkspaceResolver`: marker detection (`.repositories/odoo.git`), invalid
  workspace errors, workspace creation paths
- `ConfigService`: `odoo.conf` (ini) get/set/list, redaction, and `enable`
  side effects
- `TargetResolver`: explicit flag, cwd, only-worktree, and ambiguity errors
- `RepositoryService`: repository registry validation and planned checkout
  operations
- `WorktreeService`: full and linked worktree layout decisions
- `AddonsPathResolver`: deterministic order and ignored directories
- `VenvService`: venv path/profile resolution without installing packages
- `OdooBinService`: generated args/env/redacted args for each command purpose
  and supported Odoo version
- `RunStateStore`: sanitized args, stale pid handling, port state
- `InfoService` / `StatusService`: composed structured output without duplicate
  inference logic

`OdooBinService` deserves especially explicit tests because it is the wrapper
around a version-dependent external interface. For each supported Odoo version,
tests should assert the generated command for server start, DB initialization,
module update, tests, shell, and RPC-adjacent operations. Unsupported feature
requests should raise typed errors.

### CLI tests

CLI tests should use Click's `CliRunner` and injected fake services.

They should assert:

- command grammar and aliases
- help text for common commands
- exit codes
- concise user-facing errors
- `--json` shape for state commands
- redaction of secrets in text and JSON output

CLI tests should not verify business rules that already belong to core service
tests. The command layer is an adapter.

### Integration tests

Integration tests exercise the real local backend without a full Odoo run.

They may use:

- temporary local git repositories and bare repositories
- real filesystem symlinks
- local subprocess execution for small commands
- optional PostgreSQL checks when an environment flag is present

They should still avoid network access. Remote repository behavior can be tested
with local `file://` repositories or fake backend responses.

### Real Odoo end-to-end tests

Real-Odoo tests are valuable, but they should be opt-in.

They should run only when an explicit flag is set, for example:

```text
ODOO_CLI_E2E=1 python -m unittest discover tests/e2e
```

Expected prerequisites:

- supported Python for the CLI
- git
- PostgreSQL access
- system packages needed by the target Odoo version
- either cached local Odoo repositories or permission to fetch them

Useful environment variables:

- `ODOO_CLI_E2E_WORKSPACE`
- `ODOO_CLI_E2E_ODOO_REPO`
- `ODOO_CLI_E2E_ENTERPRISE_REPO`
- `ODOO_CLI_E2E_VERSION`
- `ODOO_CLI_E2E_DB_PREFIX`

The e2e suite should cover a small number of use-case flows from
`usecase.md`, not every command permutation:

- initialize a workspace for one Odoo version
- start the server in the background
- verify `status`, `info`, URL, ports, and log paths
- install a module with `odoo module install`, then reset the database and
  confirm the module is reinstalled (DB is the source of truth)
- update a simple module
- perform a minimal RPC login or health check when the server is running
- stop the server and confirm stale runtime state is handled

E2E tests must use unique database names, clean up best-effort, and print enough
diagnostics to understand a failure. They should be suitable for manual runs and
nightly CI, not for the default contributor loop.

## Implementation order

Each implementation step should include the matching unit tests before moving to
the next service. The real-Odoo e2e suite can arrive later, but the service
tests should grow with the implementation.

1. Create the Click entrypoint and service container.
2. Implement `core.errors`, `core.models`, and `cli.context`.
3. Implement workspace resolution (marker `.repositories/odoo.git`) and the
   `OdooConf` reader/writer over `~/.config/odoo/odoo.conf`.
4. Implement `TargetResolver`.
5. Implement filesystem-derived repositories and full worktree services.
6. Implement addons path resolution.
7. Implement venv resolution.
8. Implement `OdooBinService` and its version capability table.
9. Implement port allocation and foreground `odoo start` (write `.run/.../ports`).
10. Implement DB reset (read installed modules from DB), `odoo update`, and
    `odoo module install`.
11. Implement `odoo test` and `odoo shell`.
12. Implement `odoo config` (`get`/`set`/`list`/`enable`).

That completes the v1 surface (10 commands). The remaining steps are v2+:

13. Add the server lifecycle (`stop`, `restart`, `--background`, `.run` pid/log/
    socket/args), then `where`/`info`/`status`/`log`/`rpc`/`db shell`/`db query`/
    `doctor`/`pull`/`worktree list`/`worktree remove` and the `config` wizard.
14. Add linked worktrees and `odoo repo add`.
15. Prepare MCP/backend extension points after the local CLI is stable.

## Greenfield stance

The implementation may reuse small helpers from the current code only if they
fit the new model directly. Otherwise, prefer deleting and rebuilding around the
new architecture.

Do not preserve:

- `workspace.toml` or any CLI-specific marker/config file
- the old per-worktree `odoo.conf` generated inside each repo
- workspace-level server ports
- global mutable facts that can be inferred from source/layout/runtime state
- command modules that implement their own target/config/addons resolution
- dependencies outside stdlib plus `click`

The implementation target is:

- Click for CLI wiring and prompts
- stdlib output helpers
- a single shared `odoo.conf` at `~/.config/odoo/odoo.conf` (Odoo's standard
  auto-loaded location), written by `odoo init`
- workspace marker is the presence of `.repositories/odoo.git`
- per-instance values (addons path, db, ports) computed and passed as CLI args
  that override `odoo.conf`; v1 does not pass `--data-dir` (odoo-bin default)
- root `.run` only in v1 (just the `ports` file); `.data` isolation is v2
- runtime ports in `.run/{worktree}/{db}/ports`
- worktree versions inferred from source
- addons inferred from filesystem layout
