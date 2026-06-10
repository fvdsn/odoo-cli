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

- Debian 12 provides Python 3.11, including the standard-library `tomllib`
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
- no TOML writer dependency
- no runtime dependency installation step for the upstream bash installer

Vendoring policy:

- upstream source distributions include `click` under `odoo_cli/_vendor`
- imports go through one small CLI-layer compatibility module so distribution
  packages can switch to system `click` without touching command code
- vendored dependency licenses are kept with the vendored source

`click` should only be imported by the CLI frontend layer. Core modules must not
import `click`; they should raise typed exceptions and return structured result
objects.

TOML reading/writing:

- use `tomllib` from the standard library for reading
- write `workspace.toml` through a small internal TOML writer that supports the
  subset of TOML we generate
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
        configure.py
        config.py
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
        config.py
        target.py
        repositories.py
        worktrees.py
        addons.py
        venvs.py
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
- `config: WorkspaceConfig`

Important paths:

- `workspace.root / "workspace.toml"`
- `workspace.root / ".repositories"`
- `workspace.root / ".venvs"`
- `workspace.root / ".run"`
- `workspace.root / ".data"`
- `workspace.root / worktree_name`

`Workspace` should not do heavy work. It is a value object with path helpers.

### `WorkspaceConfig`

Parsed `workspace.toml`.

Responsibilities:

- expose workspace-level defaults
- expose repository registry
- expose per-worktree overrides
- resolve inherited Odoo settings for a target worktree
- redact secrets for display

It should not:

- infer worktree versions
- list active addon directories
- store runtime ports
- store process state
- store persistent data paths beyond configured overrides

### `RepositorySpec`

Registered repository source.

Fields:

- `name: str`
- `url: str | None`
- `enabled: bool`
- `builtin: bool`

Rules:

- repository names share one flat namespace
- `odoo` and `documentation` are enabled by default
- optional builtins such as `enterprise`, `themes`, and `upgrade` may be false
- customer addon repositories are registered by `odoo repo add`

### `Worktree`

Filesystem worktree.

Fields:

- `name: str`
- `path: Path`
- `linked_from: str | None`

Derived facts:

- version from `path / "odoo/odoo/release.py"`
- active standard repos from directories/symlinks present in the worktree
- active custom addons from filesystem discovery

`workspace.toml` does not need an entry for every full worktree. It only needs
entries for overrides and linked worktrees.

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
- `data_dir: Path`

Path rules:

- `run_dir = workspace.root / ".run" / worktree / database`
- `data_dir = workspace.root / ".data" / worktree / database`

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

- find active workspace using the requirements resolution order
- validate `workspace.toml` marker
- load config
- create initial workspace skeleton for `odoo init`

### `ConfigService`

Responsibilities:

- read/write `workspace.toml`
- merge workspace defaults with worktree overrides
- redact secrets for output
- update workspace-level config through `odoo configure`
- update worktree overrides through `odoo configure -w`

It should expose explicit methods rather than generic nested mutation wherever
the UX is still being designed.

Examples:

- `set_repository(name, url_or_false)`
- `set_worktree_odoo_overrides(worktree, overrides)`
- `clear_worktree_override(worktree, key)`

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

- creates real git worktrees for `odoo`, `documentation`, and enabled optional
  standard repositories
- skips optional repositories that lack the requested version and reports a
  warning

Linked worktree creation:

- validates `linked_from`
- validates requested version against source worktree detected version
- symlinks standard repositories from source worktree
- checks out addon repositories as real git worktrees at the linked worktree root
- writes only `linked_from` to `workspace.toml`

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
- resolve shared venv path for detected version
- apply worktree venv override if configured
- create/rebuild venv
- install Odoo requirements

### `PostgresService`

Responsibilities:

- build PostgreSQL environment from workspace config
- check connection
- create/drop databases
- run SQL
- terminate database connections before reset

PostgreSQL passwords should be passed through environment variables, not command
arguments.

### `DatabaseService`

Responsibilities:

- initialize default DB on first start
- reset DB
- install configured modules during initialization/reset
- expose `db shell` and `db query`

`db reset` should keep the `.data` lifecycle open until the design decision is
made.

### `OdooBinService`

Responsibilities:

- build all `odoo-bin` command specifications
- expose high-level builders for server start, module install, module update,
  tests, shell, and other direct Odoo invocations
- translate resolved workspace/worktree/database settings into `odoo-bin`
  command-line arguments
- include deterministic addons paths from `AddonsPathResolver`
- include per-instance data directories from `ServerInstance`
- include PostgreSQL connection settings without leaking secrets into process
  arguments
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
- resolve Odoo application credentials
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
- parse `workspace.toml` directly
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
- small fixture builders for `Workspace`, `Worktree`, `Target`, and
  `WorkspaceConfig`
- `unittest.mock` only at process/backends boundaries

High-value unit coverage:

- `WorkspaceResolver`: marker detection, invalid workspace errors, workspace
  creation paths
- `ConfigService`: TOML parsing/writing, inheritance, overrides, redaction
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
- create/reset a database and install configured modules
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
3. Implement workspace/config loading with `workspace.toml` and the
   `[odoo_cli] schema_version = 1` marker.
4. Implement `TargetResolver`.
5. Implement repository registry and full worktree services.
6. Implement addons path resolution.
7. Implement venv resolution.
8. Implement `OdooBinService` and its version capability table.
9. Implement run state, port allocation, and server start/stop.
10. Implement DB reset/update/shell/query.
11. Implement info/status/log/rpc/test.
12. Add `odoo configure -w` for worktree overrides.
13. Add linked worktrees and `odoo repo add`.
14. Prepare MCP/backend extension points after the local CLI is stable.

## Greenfield stance

The implementation may reuse small helpers from the current code only if they
fit the new model directly. Otherwise, prefer deleting and rebuilding around the
new architecture.

Do not preserve:

- old workspace filename or marker conventions
- generated `odoo.conf`
- workspace-level server ports
- global mutable facts that can be inferred from source/layout/runtime state
- command modules that implement their own target/config/addons resolution
- dependencies outside stdlib plus `click`

The implementation target is:

- Click for CLI wiring and prompts
- stdlib output helpers
- `workspace.toml` with `[odoo_cli] schema_version = 1`
- no generated `odoo.conf`
- root `.run` and `.data`
- runtime ports in `.run/{worktree}/{db}/ports`
- worktree versions inferred from source
- addons inferred from filesystem layout
