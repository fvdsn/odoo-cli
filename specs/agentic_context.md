# Odoo CLI — Agentic context engineering

This spec describes how `odoo-cli` sets up *agentic context* so that AI coding
agents — Claude Code, Codex, opencode, and GitHub Copilot (Copilot CLI, VS Code
Copilot, and the cloud coding agent) — understand the workspaces it manages
(e.g. `~/odoo`) and can run useful task workflows in them.

All of these harnesses read the `AGENTS.md` convention and a `.agents/skills`
skill dir, so the workspace `AGENTS.md` files and a `<workspace>/.agents/skills`
dir are written **unconditionally**. The Claude-specific artifacts (`CLAUDE.md`
and `<workspace>/.claude/skills`) are written **only when Claude is detected**.
See "Always-on vs Claude-only" below.

Skills install **into the workspace** (`<workspace>/.agents/skills`,
`<workspace>/.claude/skills`), not the user's global skill dirs under `~`. See
"Installed in the workspace, not globally" for the rationale and its one
discovery tradeoff.

It fleshes out the v2 line item in `requirements_v2.md` → "Agent context
generation". `requirements.md`, `usecase.md`, and `architecture.md` are the
canonical inputs for workspace structure and the derive-from-the-filesystem
philosophy this spec inherits.

Scope note: this is about the **managed workspace**, not the `odoo-cli` source
repository. The artifacts described here are written by `odoo` commands; they are
not part of the CLI's own repo.

## Goals

- Give an agent that lands anywhere in a managed workspace enough context to
  understand what the workspace is, how it is laid out, that it is managed by
  `odoo-cli`, and how to operate it.
- Ship reusable task workflows (operating odoo-cli, code review, security
  review, …) as skills bundled in the tool and installed into the **workspace's
  own** skill directories, so an agent started in the workspace picks them up
  without leaking Odoo context into the user's unrelated projects.
- Use each harness's standard mechanism, with no content duplicated across
  harnesses beyond what those mechanisms require.
- Set the workspace files up automatically as part of normal commands
  (`odoo init`, `odoo worktree create`); keep skill (re)installation on a
  separate, explicit step tied to the tool, not to repository syncing.

## Non-goals

- A bespoke per-agent configuration system. We use each harness's documented
  files and nothing more.
- Copilot-specific files. GitHub Copilot is supported through the shared
  `AGENTS.md` + `.agents/skills` convention it already reads — we add **no**
  `.github/copilot-instructions.md` and no Copilot-only skill location. Copilot
  CLI and the cloud coding agent read root/nested `AGENTS.md` by default; VS Code
  in-editor auto-detects the root `AGENTS.md` too (toggle `chat.useAgentsMdFile`).
  We deliberately do not generate `.github/copilot-instructions.md` — keeping the
  workspace free of per-tool files. Skills: Copilot CLI and VS Code Copilot both
  discover the project `.agents/skills` (alongside `.claude/skills`), so the
  bundled skills are picked up with no new location.
- A separate skills repository / distribution mechanism, for now. All skills are
  bundled in the `odoo-cli` package (see "Bundled in the tool"). This is revisited
  only when the skill set outgrows the package.
- Enumerating live workspace state (which worktrees exist, their versions,
  ports, installed modules) in any generated file. Live state is read at runtime
  via `odoo where`; baking it into a static file would rot.

## Two artifact types

The setup produces two kinds of artifact, with different lifecycles and
locations:

| Artifact | Purpose | Location | Ownership | Lifecycle |
|---|---|---|---|---|
| `AGENTS.md` | Always-on orientation + pointer to the `odoo-cli` skill | In the workspace (root + per worktree) | **User-owned** after creation | Created once at `init` / `worktree create`, never rewritten |
| Skills | odoo-cli usage detail + task workflows (review, security) | The **workspace's own** skill dirs (`<workspace>/.agents/skills`, `<workspace>/.claude/skills`) | **Tool-owned** | Bundled in the package; installed at `init`; refreshed on tool upgrade |

Orientation is project-specific, so it lives in the workspace; it stays small and
points at the skill for detail. The skills are domain knowledge, but they install
into the **workspace** rather than the user's global skill library: a global
install makes every harness preload Odoo skills in *every* project the user opens,
biasing unrelated sessions — a cost that outweighs the convenience of
discover-from-anywhere. The split still mirrors a harness fact: every harness has
one always-injected instructions file (ambient knowledge) and a separate
on-demand skill mechanism (detail loaded when relevant).

## Asset layout (markdown, not source)

The `AGENTS.md` templates and the skills are plain markdown **files shipped as
package data**, not strings embedded in Python. They are **copied verbatim** — no
templating, no substitution — so authoring is just editing or adding markdown,
never touching code.

Proposed layout inside the package (exact path TBD):

```text
odoo_cli/agent_assets/
    AGENTS.md             # root workspace orientation (+ the odoo-cli skill pointer)
    AGENTS.worktree.md    # thin per-worktree bootstrap (identical for every worktree)
    skills/
        odoo-cli/SKILL.md
        odoo-review/SKILL.md
        odoo-security/SKILL.md
```

Rules:

- Skills are discovered by **listing `skills/`** at install time, so adding a
  skill is dropping a new `skills/<name>/` folder — no code change. The installer
  copies whatever is there.
- Files are copied **as-is**. Anything that would otherwise be dynamic (worktree
  name, version, ports, …) is deferred to `odoo where`, which is exactly what keeps
  both the create-once `AGENTS.md` and the static worktree template honest.
- Assets are read through `importlib.resources` (stdlib), consistent with the
  no-extra-runtime-dependency policy; they ship as package data.

`odoo init` copies `AGENTS.md` / `AGENTS.worktree.md` into the workspace
(create-once) and the `skills/*` folders into the workspace skill dirs (tool-owned).

## Part 1 — `AGENTS.md` orientation

### Canonical file and harness links

`AGENTS.md` is the single real file. Other harnesses' always-on files are
**logical symlinks** to it (identical content, one source):

```text
~/odoo/
    AGENTS.md                 <- the real file (Codex, opencode, Copilot read it)
    CLAUDE.md -> AGENTS.md     <- Claude Code (only when Claude is detected)
```

- **Codex**, **opencode**, **Copilot CLI**, and the **Copilot cloud coding
  agent** read `AGENTS.md` natively; no extra file. **VS Code Copilot**
  auto-detects the root `AGENTS.md` (toggle `chat.useAgentsMdFile`).
- **Claude Code** reads `CLAUDE.md` (symlink), written **only when Claude is
  detected** (see "Always-on vs Claude-only").
- We add **no** Copilot-specific file: `AGENTS.md` already covers every Copilot
  surface, so there is no `.github/copilot-instructions.md`.

### Slim orientation that points at the skill

`AGENTS.md` holds a **slim, self-sufficient orientation** plus an explicit pointer
to the `odoo-cli` skill — not the full command reference. It contains:

- what the workspace is and that it is managed by `odoo-cli`;
- the layout in brief (`.repositories/`, `.venvs/`, `.run/`, and that top-level
  directories are worktrees; full vs linked);
- the essential next actions: run `odoo where` for live state,
  `odoo --help` for commands;
- a **conditional** instruction: "if an `odoo-cli` skill is available, use it to
  operate this workspace; otherwise rely on `odoo where` and `odoo --help`".

The detailed command reference and conventions live in the **`odoo-cli` skill**
(Part 2), not here, for two reasons:

- **No staleness.** `AGENTS.md` is create-once (below); the skill is refreshed on
  tool upgrade. Keeping the evolving detail in the skill means it tracks the
  installed CLI version, which a create-once file could not.
- **Lazily-loaded when present.** When a harness *has* the skill installed it
  preloads its `name`+`description` (Claude into the system prompt; Codex/opencode
  list them via a skill tool) and loads the body on demand; naming the skill in
  `AGENTS.md` is a documented way to encourage activation.

The pointer is **conditional, not assumed**, for two reasons: skills are installed
only when a harness is detected (Part 2 → "Only for installed harnesses"), so the
skill may be absent entirely; and even when installed, a harness may cap or
truncate its skill list (per Codex's docs), so it is not guaranteed to surface.
The orientation must therefore be *self-sufficient*: an agent that never sees the
skill should still not be lost — it knows it's an odoo-cli workspace and to run
`odoo where` / `odoo --help`. The slim file is the floor; the skill is the detail.

What `AGENTS.md` must **not** contain: live, derivable state (the current
worktrees, versions, ports, enabled repos, installed modules). It defers that to
`odoo where` — the same derive-from-source rule the rest of the
project follows, and what makes a create-once file safe.

### Create-once, user-owned

`AGENTS.md` is **written once and never touched again** by `odoo-cli`:

- If the file is absent, the command writes it from the bundled template.
- If it already exists and is non-empty, it is left completely alone.
- If it exists as a 0-byte placeholder, it is treated as absent and replaced by
  the bundled template.

This makes the file the user's to edit freely — no managed-block merging, no
regeneration, no clobbering. The template is bundled in the package, so writing
it needs no network.

### Root file and thin per-worktree files

The workspace root gets the orientation `AGENTS.md` (+ `CLAUDE.md` symlink). Each
worktree additionally gets a **thin** `AGENTS.md` — and *only* that, no
`CLAUDE.md` symlink:

```text
~/odoo/master/
    AGENTS.md                 <- thin bootstrap, for Codex/opencode only
```

It is a **static template, identical in every worktree** (copied verbatim — see
Asset layout): nothing worktree-specific is baked in. It says the agent is inside
a worktree of an odoo-cli workspace and must **bootstrap** the rest — "read the
workspace `../AGENTS.md` and run `odoo where`" (which resolves the current
worktree, its database, and its venv).

It exists only because many users start an agent at the worktree root, where:

- a worktree root is **not** a git repo (the git roots are the checkouts inside
  it, e.g. `master/odoo/`), and neither is the workspace root;
- **Codex** only searches down from a *git* project root ("if it cannot find a
  project root, it only checks the current directory") and **opencode** stops at
  the git worktree root. With no git root at or above the worktree, those two
  reliably read only the file at the worktree root — hence the worktree
  `AGENTS.md`.

**Claude needs no file in the worktree.** It reads `CLAUDE.md`, not `AGENTS.md`,
and walks the directory tree up to `$HOME`, so it already loads the workspace
`~/odoo/CLAUDE.md` directly — a per-worktree `CLAUDE.md` symlink would be pure
redundancy. The thin file is create-once / user-owned.

### When it is written

- `odoo init` writes the root `AGENTS.md` (+ symlink) and the first worktree's
  thin file, and installs skills (Part 2).
- `odoo worktree create` writes the new worktree's thin `AGENTS.md` (no symlink).
- Writing agent files is best-effort: a failure never fails the underlying
  command.

## Part 2 — Skills

### What they are

Skills the agent loads on demand. Initial set:

- `odoo-cli` — how to operate the workspace with odoo-cli: command reference,
  conventions, common flows. This is the detail that `AGENTS.md` points at.
- `odoo-review` — review Odoo code (style, ORM correctness, conventions).
- `odoo-security` — security review.

A skill is a directory with a `SKILL.md` (YAML frontmatter: required `name` and
`description`, plus optional scripts/references) — the [Agent Skills] open
standard that Claude Code, Codex, and opencode all implement. Each harness
preloads the `name`+`description` of every skill and loads the body only when
relevant, so they cost almost nothing until used.

### Installed in the workspace, not globally

Skills go into the **workspace's own** skill directories, not the user's global
skill library. The deciding factor is context hygiene:

- A global install makes every harness preload the Odoo skills' name+description
  in **every** project the user opens — Claude injects them into the system
  prompt, Codex/opencode list them via a skill tool. That biases unrelated, non-
  Odoo sessions into thinking they are working on Odoo. Scoping the skills to the
  workspace removes that leak entirely; they exist only where they are relevant.
- The cost is discovery scope. Every harness bounds skill search at the **git
  repo root**, and a workspace root and worktree root are **not** git repos (the
  git checkouts are nested inside, e.g. `~/odoo/19.0/odoo/`). So a harness started
  at the workspace root finds the skills, but one started **at a worktree root**
  (or with cwd inside a checkout) does not auto-load them. This is an accepted
  tradeoff: not auto-discovering at the worktree root is preferable to polluting
  every global session. The per-worktree `AGENTS.md` names the workspace-root
  skill path as a fallback so an agent there can still read it directly.

Skills go into **two** workspace dirs. Every harness discovers skills **one level
deep** (`<dir>/<name>/SKILL.md`), so each skill is a direct child, named `odoo-*`
to namespace it and avoid collisions with the user's own skills:

| Workspace skill dir | Read by | Installed |
|---|---|---|
| `<workspace>/.agents/skills/` | Codex, opencode, Copilot CLI, VS Code Copilot | **always** |
| `<workspace>/.claude/skills/` | Claude Code, opencode, VS Code Copilot | only when Claude is detected |

`.agents/skills` is the shared AGENTS.md-convention dir that every non-Claude
harness reads, so it is written unconditionally — no per-tool probe. opencode and
VS Code Copilot read *both* dirs (verified), so neither needs a location of its
own. (opencode also reads `.opencode/skills/`, Codex reads project-checked-in
`.agents/skills`, Copilot CLI reads `~/.copilot/skills/`, and VS Code Copilot's
primary project dir is `.github/skills/`, but since they all read the two dirs
above we write no separate location for any of them.)

So an install always creates `<workspace>/.agents/skills/odoo-review/SKILL.md`, …
and `<workspace>/.claude/skills/odoo-review/SKILL.md`, … additionally when Claude
is detected. The directory name becomes the invocation name (`/odoo-review`).

### Always-on vs Claude-only

The split is deliberate:

- **Always written:** the workspace `AGENTS.md` files (root + per worktree) and
  `<workspace>/.agents/skills`. The `AGENTS.md` convention is read by every
  harness we target (and is a harmless, ignorable file for any that don't), and
  `.agents/skills` is the neutral cross-tool skill dir — not owned by any one
  tool — so there is no tool to "detect" for it. Writing them unconditionally
  keeps setup predictable and future-proofs any new AGENTS.md harness.
- **Claude-only, detected:** `CLAUDE.md` (the workspace symlink) and
  `<workspace>/.claude/skills`. These are Claude Code's own files, so we write
  them only when Claude is present, rather than littering the workspace with a
  `.claude/` dir for a tool the user does not use.

**Claude detection** — `claude` on `PATH`, the `~/.claude` config dir, or a
Claude **desktop** app config dir (`~/Library/Application Support/Claude` on
macOS, `~/.config/Claude` on Linux, `%APPDATA%/Claude` on Windows). The desktop
app hosts Claude Code, which reads `.claude/skills` and `CLAUDE.md`, so its
presence counts even when the `claude` CLI is absent from `PATH`.

Detection is at install time, so the refresh step (below) picks up Claude if it
appeared since `odoo init` — adding `CLAUDE.md` and `<workspace>/.claude/skills`
on the next run.

### Bundled in the tool

All skills ship **inside the `odoo-cli` package**, as the markdown folders under
`agent_assets/skills/` (see Asset layout). Installing copies them into the
workspace skill dirs as plain folders — no `.git`, no symlinks, no network, no
temp clone:

- list `agent_assets/skills/` and copy each `<name>/` folder into every workspace
  skill dir, verbatim;
- best-effort: a failure never fails the underlying command.

Because the installer just copies the directory, adding or editing a skill is a
markdown-only change — no source edit.

This is the simplest thing that works, and it makes every skill **version-matched
to the installed binary** — exactly right for the `odoo-cli` usage skill, and fine
for the rest for now. A separate skills repository with its own update channel
(and, since the repo could be shaped as a plugin marketplace, native
auto-updates) is deferred until the skill set outgrows the package or a better
distribution mechanism emerges (see Future work).

### Lifecycle: install at init, refresh with the tool

- **Install** happens during `odoo init`.
- **Legacy migration** — earlier versions installed skills into the global
  `~/.agents/skills` / `~/.claude/skills`. `init` now prunes the marker-bearing
  `odoo-*` folders from those global dirs (`prune_legacy_global_skills`), so an
  upgrade stops leaking Odoo context into unrelated sessions. Only marker-bearing
  folders are removed; the user's own global skills are untouched.
- **Refresh** is tied to the **tool**, not to `odoo pull` — repository syncing and
  skill updates are unrelated. Because the skills are bundled, a refresh is just
  re-copying the package's skill folders. In v1, re-running `odoo init` is the
  refresh path: init/install behaves the same as sync for marker-owned skills.
  A dedicated `odoo skills sync` command can be added later if the workflow needs
  a smaller explicit entry point.
- **Ownership / removal** — ownership is recorded by a **marker file inside each
  installed folder** (e.g. `<skill>/.installed-by-odoo-cli`), written at install
  time. `odoo-cli` only ever overwrites or prunes folders that carry the marker: a
  refresh re-copies the bundled set (re-stamping the marker) and removes
  marker-bearing folders no longer bundled; an uninstall removes only
  marker-bearing folders. A folder **without** the marker is left untouched — even
  if its name collides with a bundled skill (a user-authored or third-party Odoo
  skill), in which case the install skips it and warns rather than clobbering.

  The `odoo-*` naming is just namespacing to reduce collisions; it is **not** the
  ownership signal. The workspace skill dirs may also hold the user's own skills,
  so deleting by name prefix would be too blunt — the marker is the deliberate
  exception to the project's "no metadata" preference, scoped to a file inside
  folders we create.

### Footprint and tradeoffs

- **No cross-project leak** — because skills live in the workspace, they never
  appear in the user's unrelated projects. This is the whole reason for the
  workspace-local choice (a global install preloads Odoo skill metadata into
  every session). The `description` frontmatter still scopes auto-invocation and
  the `odoo-*` names avoid collisions, but the primary guard is location.
- **Not auto-discovered at a worktree root** — the accepted cost. A harness whose
  cwd is a worktree root (or inside a checkout) sits below/outside the workspace
  root's discovery range, so it does not auto-load the skills; the per-worktree
  `AGENTS.md` points at the workspace-root skill path as a fallback.
- **Writes into the workspace** — installing always writes
  `<workspace>/.agents/skills` and additionally `<workspace>/.claude/skills`
  **only when Claude is detected** (see "Always-on vs Claude-only"). It must be
  idempotent and cleanly removable (drop only marker-bearing folders).

## Harness reference (researched)

Recorded so implementation does not need to re-derive it.

All harnesses discover **project** skills one level deep and bound the search at
the **git repo root** (verified 2026). We rely on the project dir we write
(`.agents/skills`, and `.claude/skills` for Claude), not the global `~` dirs.

| Harness | Always-on file | Project skills dir(s) we use | Other dirs read | Discovery notes |
|---|---|---|---|---|
| Claude Code | `CLAUDE.md` (→`AGENTS.md`); walks up to `$HOME` | `.claude/skills/` | `~/.claude/skills/` (global) | starting dir + parents **up to the git repo root**; nested dirs on demand |
| Codex | `AGENTS.md`; searched only within a git project root | `.agents/skills/` | `~/.agents/skills/` (global) | cwd up to the git **repo root**; no project root ⇒ **only cwd** |
| opencode | `AGENTS.md`; up to git worktree root | `.agents/skills/`, `.claude/skills/` | `.opencode/skills/`; global `~/.config/opencode/skills`, `~/.claude/skills`, `~/.agents/skills` | cwd up to the **git worktree root** |
| Copilot CLI | `AGENTS.md` (root + cwd) by default; also `.github/copilot-instructions.md`, `CLAUDE.md` | `.agents/skills/` | `~/.agents/skills`, `~/.copilot/skills` | one level; searches repo root + cwd |
| VS Code Copilot | `.github/copilot-instructions.md` (default-on); `AGENTS.md` auto-detected at root (toggle `chat.useAgentsMdFile`) | `.agents/skills/`, `.claude/skills/` | `.github/skills/` (primary), `~/.copilot/skills`; `chat.agentSkillsLocations` adds more | one level; the opened workspace folder |
| Copilot cloud coding agent | `AGENTS.md` (root + nested) by default; `.github/copilot-instructions.md`, `.github/instructions/**`, `CLAUDE.md`, `GEMINI.md` | in-repo `.github/skills/` | — | runs in-repo; out of scope for workspace install |

Sources: Claude Code memory, skills (+ best practices) & plugin-marketplace docs;
openai/codex AGENTS.md, skills & plugins docs, and #6038; opencode rules & skills
docs and #2225; GitHub Copilot custom-instructions docs (VS Code
`agent-customization` docs, Copilot CLI & cloud-agent docs); GitHub "Copilot now
supports Agent Skills" changelog (2025-12-18).

## Implementation sketch

Deliberately small — copying a handful of markdown files needs functions, not a
class hierarchy. It follows existing conventions: env / `which` injected with
defaults (as in `core/paths.py`, `core/venvs.py`), write-if-absent (as in
`WorkspaceResolver.ensure_default_conf`), and best-effort steps rendered by the
command (as in `commands/init.py`).

### Files

- `odoo_cli/agent_assets/` — the markdown shipped as package data
  (`AGENTS.md`, `AGENTS.worktree.md`, `skills/odoo-<name>/SKILL.md`). Read at
  runtime via `importlib.resources.files("odoo_cli") / "agent_assets"` (stdlib;
  no `__init__.py` needed for traversal).
  - **Packaging** — `pyproject.toml` uses `packages = ["odoo_cli"]`; the data
    files only ship if included. hatchling includes VCS-tracked files under the
    package, so committed `.md` files ship, but this is verified by a test
    (below), not assumed.
  - **Reading is via `Traversable`, not a `Path`.** `files()` returns a
    `Traversable`, which on Python 3.10 and for zip/wheel installs is **not** a
    real filesystem path — do **not** pass it to `shutil.copytree`. Read single
    templates with `.read_text()`, and copy a skill folder with a tiny recursive
    helper over `.iterdir()` / `.is_dir()` / `.read_bytes()`, materializing onto
    the destination `Path`. (`importlib.resources.as_file` on a *directory* is
    unreliable before 3.12, hence the manual walk.)
- `odoo_cli/core/agent_assets.py` — a module of plain functions, named to match
  the data dir it sources from (no import clash; different package):

```python
def write_workspace_docs(workspace, env=None, which=shutil.which) -> list[Path]:
    # root AGENTS.md from template if absent (always);
    # + CLAUDE.md -> AGENTS.md if absent AND Claude is detected
def write_worktree_docs(worktree) -> list[Path]:
    # thin AGENTS.md if absent (no CLAUDE.md symlink — Claude climbs to the root)

def install_skills(root, env=None, which=shutil.which) -> SkillsResult:
    # into each workspace skill dir under `root`: copy bundled skills + stamp
    # <skill>/.installed-by-odoo-cli; prune marker-bearing folders no longer
    # bundled; skip+warn on a marker-less name collision. Idempotent (= sync).
def uninstall_skills(root, env=None, which=shutil.which) -> list[Path]:
    # remove only marker-bearing folders from the workspace skill dirs

def _skill_dirs(root, env, which) -> set[Path]:
    # <root>/.agents/skills always; <root>/.claude/skills only if _claude_present
def _claude_present(env, which) -> bool:
    # which("claude") or ~/.claude is a dir or a Claude desktop config dir exists
```

Primitives: write-if-absent is `path.exists()`; copying a skill folder is the
recursive `Traversable` walk above (not `shutil.copytree`, since the source is a
resource, not a path); symlink is `os.symlink("AGENTS.md", …)` (relative target;
the project targets Debian/Ubuntu, so symlinks are fine). No service-container
entry — these are stateless functions, called directly like `core/paths` already
is.

### Wiring

- `commands/init.py` — after the workspace / first worktree / venv steps, call
  `write_workspace_docs`, `write_worktree_docs`, and `install_skills(workspace.root)`,
  all inside one best-effort guard that warns instead of failing `init`.
- `commands/worktree.py` — call `write_worktree_docs` for the new worktree.
- A future `odoo skills` command group (`sync` = `install_skills`, plus
  `uninstall`) can expose the same refresh/removal primitives directly; deferrable
  because re-running `odoo init` already refreshes marker-owned skills.

### Tests

`tests/unit/test_agent_assets.py`, filesystem-only (no process runner):
write-if-absent leaves an existing file untouched; symlink only at the workspace
root; detection matrix via a fake `which` + temp `HOME`, with skills installed
under a temp workspace root (claude → `<root>/.claude/skills`; codex-only and
opencode-only → `<root>/.agents/skills`; none → only `.agents/skills`);
`install_skills` copies skills and stamps the marker, a re-run
after a skill is dropped prunes the marker-bearing folder, a marker-less folder
(even one whose name collides with a bundled skill) is left untouched, and
`uninstall_skills` removes only marker-bearing folders.

Plus a **package-data test**: assert the assets are discoverable through
`importlib.resources` (the `AGENTS.md` template and at least the expected skill
folders), which catches a wheel that failed to ship `agent_assets/`. The
recursive-copy helper is exercised against the real bundled resources so the
`Traversable` path (not just a temp-dir `Path`) is covered.

## Open questions

- **Refresh command** — whether a standalone `odoo skills sync` is worth adding
  once re-running `odoo init` is no longer enough.

## Future work

- **Separate skills repository** — once the bundled set is too big to manage, move
  skills to their own repo with an independent update channel. Shaping that repo
  as a plugin marketplace (Claude `.claude-plugin/marketplace.json`, Codex
  `.codex-plugin/plugin.json`) would also let users opt into native background
  auto-updates (`claude plugin marketplace add …`), instead of / in addition to
  the copy install. Deferred until the need is real.

## Out of scope (for now)

- Copilot-specific files (`.github/copilot-instructions.md`, a Copilot-only skill
  dir). Copilot is covered through the shared `AGENTS.md` + `.agents/skills`;
  see Non-goals.
- MCP frontend (`requirements_v3.md` → "MCP frontend") — a separate, richer
  integration path; this spec is only about file-based agent context.
- Generating agent context for the `odoo-cli` source repo itself (it already has
  its own `AGENTS.md`).

[Agent Skills]: https://agentskills.io
[openai/codex#6038]: https://github.com/openai/codex/issues/6038
[anomalyco/opencode#2225]: https://github.com/anomalyco/opencode/issues/2225
