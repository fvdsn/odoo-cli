# Machine-Readable Output Contract

The CLI is consumable by programs (a web frontend, an agent, a supervisor)
shelling out to it. This document is the contract those callers rely on;
changing a field name, an error code, or an exit code documented here is a
breaking change.

## Ground rules

- A command invoked with `--json` prints **exactly one JSON document to
  stdout** and nothing else there; progress and status lines move to stderr.
- Exit codes: `0` success, `1` user-facing failure, `2` usage error, `130`
  aborted; terminal-attached children (`start`, `shell`, `test`) propagate
  their own exit code.
- No command ever prompts. Safety gates are bypassed with flags
  (`--force`, `--purge`), never interactively.
- On failure in `--json` mode, stdout carries an error envelope:

  ```json
  {"error": {"code": "worktree_not_found", "message": "…", "hint": "…"}}
  ```

  `code` is the snake_case name of the core exception class
  (`odoo_cli/core/errors.py`); `hint` may be null. Subprocess failures
  (`process_failed`) additionally carry `argv`, `returncode`, `stderr`.

## Queries

- `odoo where --json` — the full run contract. Beyond the resolved facts
  (workspace, worktree, version, database, venv, addons_path, ports), it
  carries everything an external supervisor needs to spawn the server
  itself: `python`, `odoo_bin`, `cwd`, `env`, `command` (argv list), plus
  `postgres` `{host, port, user}` (null = unset/local defaults; the
  password stays in `odoo_conf`).
- `odoo worktree list --json` — `{"worktrees": [{name, path, linked_from,
  version, valid, repos}]}`; `version` is null for a broken checkout;
  `repos` lists the real (non-symlink) checkouts as `{name, branch}` with
  `branch` null when HEAD is detached.
- `odoo db list --json` — `{"databases": [{name, size_bytes, owner,
  version, filestore}]}`; `version` is null for a non-Odoo database,
  `filestore` is the directory path or null.
- `odoo config list --json` — unchanged; secrets redacted without
  `--reveal`.

## Mutations

Each emits a small outcome document; the field names mirror the human
output. `worktree create`/`rm`, `db reset`/`clone`/`rename`,
`module install`, `update`, `pull`, `fetch`, `venv`, `repo add`/`enable`,
`test` all accept `--json`. (`init` bootstraps the workspace interactively
on a human's machine and `start`/`shell` are terminal-attached; they have
no JSON mode.)

## External dependencies

Every command about to load modules (`test`, `module install`, `update`,
`db reset`, `start`, `shell`) first ensures the manifest-declared python
dependencies of the modules that run will load are importable in the venv:
missing distributions are auto-installed, and an installation failure is
the typed error `external_dependency_not_installable` (never a raw
odoo-bin traceback). Venv creation and `odoo venv` install the full set
derived from all manifests on disk, best-effort.

## Concurrency

Concurrent invocations against one workspace are safe: venv creation,
database create/init, and bare-repo replacement serialize on flock-based
lock files (`util/locks.py`); port reservation was already atomic. A
waiting process blocks until the holder finishes, then re-reads state
(e.g. the second of two concurrent `ensure_initialized` calls finds the
database initialized and does nothing).
