# Odoo CLI requirements — v2

This document tracks requirements deferred out of v1. `requirements.md` is the
canonical v1 spec; items here are explicitly out of scope for the first version
and will be designed/promoted later.

## Configurable Odoo application credentials
 - v1 does not manage Odoo login credentials and ships no command that needs
   them; when `odoo rpc` lands in v2 it initially assumes the development
   default `admin` / `admin` (see `requirements.md` → "Odoo application credentials")
 - v2 makes the Odoo login configurable, separate from the PostgreSQL credentials
 - likely stored in `odoo.conf` (decide on concrete keys; note `admin_passwd` in
   `odoo.conf` is the database-management master password, NOT the admin user login)
 - worktree/database-specific overrides to be considered
 - commands that need Odoo authentication use the resolved credentials
 - informational commands may show the configured login but never print the
   password unless explicitly requested

## Deferred from v1 (internal-testing scope reduction)
v1 was scoped to a minimal command set for internal testing (init, config, repo
— add/enable, worktree create — full and linked, venv, start, where, module
install, update, test, db reset, shell). The following were specced as v1 but
pushed to v2; they keep a `[v2]` tag inline in `requirements.md`:

 - **Server lifecycle** — `odoo stop`, `odoo restart`, and `odoo start --background`.
   v1 is foreground-only: `odoo start` runs in the terminal, Ctrl-C to stop, and
   `.run/{worktree}/{db}/` holds only the `ports` file. v2 adds background mode,
   the pid/socket/args/log files under `.run/`, and restart from sanitized args.
 - **Per-instance persistent data** — isolating each `(worktree, db)`'s data under
   `.data/{worktree}/{db}/` and passing it as `--data-dir`. v1 uses odoo-bin's
   default data location, shared by all dbs/servers (filestore is still namespaced
   per database name, but sessions and the rest of the data_dir are shared). v2
   also decides whether `db reset` clears that database's filestore.
 - **`odoo config` wizard** — the bare interactive `odoo config` (postgres
   connection, enterprise, dev mode, ...). v1 keeps only `get`/`set`/`list`.
   For enterprise the wizard delegates to `odoo repo enable`.
 - **`odoo venv --apt` / no-venv mode** — running Odoo against system-wide
   python packages installed with apt, possibly without any venv at all
   (v1 always creates a venv, with uv or `python3 -m venv` + pip).
 - **Agent context generation** — workspace files for AI coding agents:
   CLAUDE.md and skills, plus the major agent-harness formats and a
   vendor-neutral AGENTS.md. v1 creates no agent files (the `.claude/`
   directory was dropped from the v1 workspace layout).
 - **`odoo info`** and **`odoo status`** — overview / status views (`odoo where`,
   the resolved-context view, stayed in v1).
 - **`odoo log`** — log viewer with `--follow`/`--date`/`--search` (needs the v2
   `.run/.../log` file; v1 logs to the terminal).
 - **`odoo rpc`** — path-based RPC for agents.
 - **`odoo db shell`** and **`odoo db query`** — thin wrappers over `psql`.
 - **`odoo worktree list`** and **`odoo worktree remove`**.
 - **`odoo doctor`** — setup diagnostics.
 - **`odoo pull` / `odoo fetch`** — repository sync.

## Already-identified v2 scope (support workflows)
These carry a `[v2]` tag in `requirements.md` and will be fleshed out here:
 - `odoo dump` / `restore` / `neutralize` — database lifecycle for support
 - `odoo checkout` — branch/version switching in a worktree-first model
 - `odoo scaffold` — module skeleton generation

(Linked worktrees and `odoo repo add` were promoted to v1 so support users can
validate them early.)

## `odoo fetch` and `odoo pull` (agreed design)

Two git-faithful commands that resolve the open questions left in
`requirements.md` → "Future commands → `odoo pull` / `odoo fetch`".

### Model recap

`.repositories/<repo>.git` are bare repos that mirror origin into their own
`refs/heads/*` (`+refs/heads/*:refs/heads/*`). A worktree holds one git worktree
per repo, each on a branch named after the worktree. A **version worktree**
(`19.0`, `master`, `saas-19.3`) sits on the mirror branch itself; a **feature
worktree** (`19.0-fix`, `customer-b`) sits on a local-only branch. Branches carry
no recorded upstream in this model, so pull derives what a checkout tracks from
the branch name via `infer_base_version` (`19.0-fix` → `19.0`; `master` →
`master`; `customer-b` → none).

### `odoo fetch [repo…]`

- Fetches every repo in `.repositories` (or only the named ones) from origin.
- Picks up new commits on non-checked-out branches **and brand-new branches**
  (e.g. a freshly released `20.0`, so `worktree create 20.0` then works).
- Never touches a working tree. Branches a worktree has checked out are excluded
  from the bare-repo fetch (git refuses to update them); those advance via pull.
- Per-repo outcome; a repo with no origin remote or an incomplete clone is
  skipped with a note, the rest still fetch.

### `odoo pull [-w WORKTREE]`

- Target: the current worktree (from cwd) or `-w`. Acts on **every checkout** in
  the worktree.
- For each checkout: `base = infer_base_version(branch)`; fetch `origin <base>`
  by name (sidesteps the mirror ambiguity — we always read origin's real tip),
  then **`merge --ff-only`**. Outside `--json` the merge streams to the
  terminal: on a blobless clone a big fast-forward downloads every changed
  file, and minutes of silence invite the Ctrl-C that leaves the working tree
  mixing two commits. Divergence is decided beforehand with
  `merge-base --is-ancestor` (a streamed merge has no captured stderr to
  classify), so a merge failure can only mean the checkout itself died.
  Outcomes:
  - **advanced** (`<old>..<new>`) or **already up to date** — the happy path for
    version worktrees and not-yet-diverged feature branches.
  - **skipped, diverged** — a feature branch with its own commits can't
    fast-forward; print the exact `git -C <checkout> pull --rebase origin <base>`
    (or `--no-rebase` to merge) for the user to run by hand.
  - **skipped, no tracked version** — `infer_base_version` is None, or origin has
    no `<base>` branch (e.g. an addon repo branched off its default branch).
  - **skipped, uncommitted changes** — the checkout is dirty; commit or stash
    first.
  - **skipped, interrupted fast-forward** — the merge died mid-checkout
    (Ctrl-C, network drop while fetching blobs); the working tree may mix two
    commits. Print the exact `git -C <checkout> reset --hard FETCH_HEAD` that
    finishes the update.
- **Never interactive, per-repo, non-destructive.** ff-only only; one repo that
  can't advance is skipped with guidance, the rest still pull; a final summary
  lists what moved and what was skipped. No `--rebase`/`--merge` flags (they can
  stop mid-loop on conflicts — users who want that run git directly).
- **Linked worktree** → its symlinked checkouts resolve to the source's, so pull
  advances the source and notes "linked from `<source>`".
- **No venv work.** A version change (master rolling) is handled by `odoo start`,
  which already rebuilds the venv when the detected version retargets it.

### Deliberately deferred

- `--no-fetch` / offline pull, and real remote-tracking refs
  (`refs/remotes/origin/*`). The everyday `odoo pull` fetches over the network
  like `git pull`, so neither is needed yet. Remote-tracking refs become worth it
  when `odoo status` (ahead/behind without a network call) is built; revisit
  then.
- `odoo pull --all` (a "morning sync" across worktrees).

## Parked ideas
 - offload `odoo.conf` resolution to odoo-bin itself (an odoo-bin command that
   prints the resolved config path/contents), instead of the CLI always passing
   `-c ~/.config/odoo/odoo.conf`; revisit if/when odoo-bin grows such a command
   — part of the broader convention-migration direction, see `requirements_v3.md`
   → "Convention migration into odoo-bin"
