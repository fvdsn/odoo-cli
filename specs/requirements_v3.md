# Odoo CLI requirements — v3 (Platform)

This document tracks the v3 "platform" phase: turning the local CLI into a
foundation that AI agents, cloud services, and advanced workflows can build on.
`requirements.md` (v1) and `requirements_v2.md` are the canonical earlier specs.
Nothing here is committed scope yet — these are design intents, collected so the
earlier phases don't paint us into a corner, to be fleshed out once v2 is stable.

## Convention migration into odoo-bin

Timing note: tracked in this document for convenience, but this is not v3-gated
work — the co-speccing should happen now (v1-era), and delegation lands per Odoo
version as odoo-bin gains conventions.

 - direction (CTO): rework odoo-bin so that `odoo-bin start`, `odoo-bin test`,
   ... adopt the same conventions as the CLI (derived db name, addons discovery,
   port allocation, dev-mode defaults), thinning the wrapping further
 - model: the CLI is the fast-moving lab — conventions are invented and proven
   in the CLI, the good ones are upstreamed into odoo-bin, and the CLI polyfills
   them for older Odoo versions
 - mechanism: `OdooBinService`'s capability table delegates per version
   ("version ≥ X: pass nothing, odoo-bin derives it; version < X: the CLI
   computes and passes args"); the table feature-detects where conventions live
 - hard boundary — what can never migrate down: anything that runs before
   odoo-bin can run, or spans instances/versions — repo cloning/management,
   venv creation (odoo-bin runs inside the venv it would have to create),
   worktrees and linked worktrees, workspace init, cross-version operations
 - the CLI must be built as if it fully owns the conventions — it does, for
   17.0–19.0, for years; the migration changes what the CLI gets to delete
   later, not what gets built now
 - divergence risk: odoo-bin must implement the same conventions, not cousins
   of them — `requirements.md` (db naming, addons-path order, ports-file
   semantics) is the reference spec and should be reviewed by whoever does the
   odoo-bin rework before it starts
 - open: where does odoo-bin keep runtime state (e.g. allocated ports) once it
   owns allocation? It knows nothing of the workspace `.run/`. On versions
   where odoo-bin owns a convention, the CLI should read odoo-bin's state
   rather than maintain a competing copy
 - related: the parked idea in `requirements_v2.md` (odoo-bin resolving and
   reporting its own config) is the same direction of travel
 - odoo-bin should also own *initial* `odoo.conf` creation (e.g. an
   `odoo-bin config init`), so the file is created at the location odoo-bin
   itself resolves — eliminating the CLI/odoo-bin config-location mismatch
   class at the source instead of defending against it with explicit `-c`
   - ordering: conf creation needs a runnable odoo-bin, so `odoo init` must
     clone, create the worktree, and set up the venv first; on versions
     without it, the CLI polyfills (writes the standard location, passes `-c`)
   - split of responsibilities: odoo-bin owns the file's location, existence,
     and format; the CLI applies its opinionated dev defaults (`dev_mode`,
     `log_level`, demo) afterwards through the normal `config set` path
 - once conventions are in core, manual `odoo-bin` runs genuinely behave the
   same as CLI runs, completing the thin-wrapper rationale for the shared
   `odoo.conf` at the standard location

## MCP frontend
 - expose CLI operations as MCP tools for AI agents (`odoo-mcp` / `odoo mcp serve`)
 - MCP tools call the same core services as CLI commands; no business logic in
   the frontend (see `architecture.md` → dependency rules)
 - builds on v2's machine-readable groundwork: `--json` output, `odoo rpc`,
   `odoo status`, configurable Odoo credentials
 - tool design (granularity, schemas, auth) to be defined

## Cloud backend
 - candidates: Odoo.sh, managed workspaces, managed databases, cloud runners
 - the `Backend` interface is deliberately not defined before v3 (see
   `architecture.md` → "Backend seam (deferred)"): an interface extracted from a
   single implementation is usually the wrong one, so it is extracted when this
   second implementation exists to shape it
 - a cloud backend may execute an `OdooBinCommand` by translating it into a
   remote job, or reject unsupported capabilities through typed errors
 - the CLI grammar (commands, target flags, resolution rules) must not change
   per backend

## Extensions
 - advanced workflows packaged as extensions that expose CLI commands and/or MCP
   tools while reusing the same core and backend APIs
 - candidates: support workflows, Odoo.sh workflows, dump/restore/neutralize
   variants, upgrade flows, export tooling
 - extensions must not redefine workspace resolution, target resolution, addons
   path resolution, venv rules, or server lifecycle
 - packaging and discovery mechanism (e.g. entry points) to be defined

## Open questions
 - `odoo repo enable` vs existing linked worktrees: enable skips linked
   worktrees, and their symlinks only cover repos the source had at creation
   time — so an existing linked worktree never gains a later-enabled repo
   (manual symlink or recreation required). A candidate fix is for enable to
   also symlink the repo into every linked worktree whose `odoo/` points at an
   updated source. Deliberately left to real user feedback rather than design;
   resolve when the v1/v2 testers hit it.
 - distribution: does the MCP frontend ship in the same package as the CLI or
   separately?
 - authentication and secret handling for cloud backends
 - capability negotiation between frontends and backends: what does a command or
   MCP tool do when the active backend cannot support it?
