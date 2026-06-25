# Odoo CLI — Agentic context engineering

This spec describes how `odoo-cli` sets up *agentic context* so that AI coding
agents — Claude Code, Codex, opencode, and GitHub Copilot (Copilot CLI, VS Code
Copilot, and the cloud coding agent) — understand the workspaces it manages
(e.g. `~/odoo`) and can run useful task workflows in them.

All of these harnesses read the `AGENTS.md` convention and the shared
`~/.agents/skills` skill dir, so the workspace `AGENTS.md` files and that skill
dir are written **unconditionally**. The Claude-specific artifacts (`CLAUDE.md`
and `~/.claude/skills`) are written **only when Claude is detected**. See
"Always-on vs Claude-only" below.

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
  review, …) as skills bundled in the tool and installed into the
  agent harnesses' global skill directories, so they are available regardless of
  where the agent is started.
- Use each harness's standard mechanism, with no content duplicated across
  harnesses beyond what those mechanisms require.
- Set the workspace files up automatically as part of normal commands
  (`odoo init`, `odoo worktree create`); keep skill (re)installation on a
  separate, explicit step tied to the tool, not to repository syncing.

## Non-goals

- A bespoke per-agent configuration system. We use each harness's documented
  files and nothing more.
- Copilot-specific files. GitHub Copilot is supported through the shared
  `AGENTS.md` + `~/.agents/skills` it already reads — we add **no**
  `.github/copilot-instructions.md` and no Copilot-only skill location. Copilot
  CLI and the cloud coding agent read root/nested `AGENTS.md` by default; VS Code
  in-editor auto-detects the root `AGENTS.md` too (toggle `chat.useAgentsMdFile`).
  We deliberately do not generate `.github/copilot-instructions.md` — keeping the
  workspace free of per-tool files. Skills: Copilot CLI and VS Code Copilot both
  discover
  `~/.agents/skills` (alongside `~/.claude/skills`), so the bundled skills are
  picked up with no new location.
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
| Skills | odoo-cli usage detail + task workflows (review, security) | The harnesses' **global** skill dirs (`~/...`), not the workspace | **Tool-owned** | Bundled in the package; installed at `init`; refreshed on tool upgrade |

Orientation is project-specific, so it lives in the workspace; it stays small and
points at the skill for detail. Skills are domain knowledge that isn't tied to
any directory, so they live in the global skill library where they are found from
anywhere. The split also mirrors a harness fact: every harness has one
always-injected instructions file (ambient knowledge) and a separate on-demand
skill mechanism (detail loaded when relevant).

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
(create-once) and the `skills/*` folders into the global skill dirs (tool-owned).

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

### Installed globally, not in the workspace

Skills go into each harness's **user-global** skill directory, not the
workspace. This solves a real discovery problem:

- Skills are domain knowledge, not tied to a directory — the global library is
  where they belong, and from there they are found no matter where the agent
  starts (workspace root, a worktree, or inside a checkout).
- The alternative (skills in the workspace) does **not** discover reliably for
  the common "start at the worktree root" case: harnesses scan from the cwd only
  up to the git repo root, and there is no git root at or above a worktree, so
  workspace-level skills fall out of range for Codex/opencode. Global install
  avoids this entirely and keeps the workspace free of skill files and symlinks.

Skills go into **two** global dirs. Every harness discovers skills **one level
deep** (`<dir>/<name>/SKILL.md`), so each skill is a direct child, named `odoo-*`
to namespace it and avoid collisions with the user's own skills:

| Global skill dir | Read by | Installed |
|---|---|---|
| `~/.agents/skills/` | Codex, opencode, Copilot CLI, VS Code Copilot | **always** |
| `~/.claude/skills/` | Claude Code, opencode, VS Code Copilot | only when Claude is detected |

`~/.agents/skills` is the shared AGENTS.md-convention dir that every non-Claude
harness reads, so it is written unconditionally — no per-tool probe. opencode and
VS Code Copilot read *both* dirs (verified), so neither needs a location of its
own. (opencode also reads `~/.config/opencode/skills/`, and Copilot CLI also
reads `~/.copilot/skills/`, but since they read the two dirs above we write no
separate location for either.)

So an install always creates `~/.agents/skills/odoo-review/SKILL.md`, … and
`~/.claude/skills/odoo-review/SKILL.md`, … additionally when Claude is detected.
The directory name becomes the invocation name (`/odoo-review`).

### Always-on vs Claude-only

The split is deliberate:

- **Always written:** the workspace `AGENTS.md` files (root + per worktree) and
  `~/.agents/skills`. The `AGENTS.md` convention is read by every harness we
  target (and is a harmless, ignorable file for any that don't), and
  `~/.agents/skills` is the neutral cross-tool skill dir — not owned by any one
  tool — so there is no tool to "detect" for it. Writing them unconditionally
  keeps setup predictable and future-proofs any new AGENTS.md harness.
- **Claude-only, detected:** `CLAUDE.md` (the workspace symlink) and
  `~/.claude/skills`. These are Claude Code's own files, so we write them only
  when Claude is present, rather than littering `~/.claude` for a tool the user
  does not use.

**Claude detection** — `claude` on `PATH`, the `~/.claude` config dir, or a
Claude **desktop** app config dir (`~/Library/Application Support/Claude` on
macOS, `~/.config/Claude` on Linux, `%APPDATA%/Claude` on Windows). The desktop
app hosts Claude Code, which reads the same `~/.claude/skills` and `CLAUDE.md`,
so its presence counts even when the `claude` CLI is absent from `PATH`.

Detection is at install time, so the refresh step (below) picks up Claude if it
appeared since `odoo init` — adding `CLAUDE.md` and `~/.claude/skills` on the
next run.

### Bundled in the tool

All skills ship **inside the `odoo-cli` package**, as the markdown folders under
`agent_assets/skills/` (see Asset layout). Installing copies them into the three
global dirs as plain folders — no `.git`, no symlinks, no network, no temp clone:

- list `agent_assets/skills/` and copy each `<name>/` folder into every global
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
  ownership signal. The global skill dirs are shared territory, so deleting by
  name prefix would be too blunt — the marker is the deliberate exception to the
  project's "no metadata" preference, scoped to a file inside folders we create.

### Footprint and tradeoffs

- **Cross-project visibility** — global skills appear in all the user's projects,
  not just Odoo ones. Acceptable for domain-scoped skills: the `description`
  frontmatter scopes auto-invocation ("for Odoo codebases…"), and the `odoo-*`
  names avoid collisions.
- **Writes into home dirs** — installing always writes under `~/.agents` (the
  neutral cross-tool dir) and additionally under `~/.claude` **only when Claude
  is detected** (see "Always-on vs Claude-only"). Consistent with it already
  owning `~/.config/odoo/odoo.conf`, and it must be idempotent and cleanly
  removable (drop only marker-bearing folders).

## Harness reference (researched)

Recorded so implementation does not need to re-derive it.

| Harness | Always-on file | Global skills dir | Discovery notes |
|---|---|---|---|
| Claude Code | `CLAUDE.md` (→`AGENTS.md`); walks up to `$HOME` | `~/.claude/skills/` | one level; metadata preloaded into system prompt; follows symlinks |
| Codex | `AGENTS.md`; searched only within a git project root | `~/.agents/skills/` | one level; follows symlinked skill folders; no git root ⇒ only cwd |
| opencode | `AGENTS.md`; up to git worktree root | reads home-level `~/.claude/skills`, `~/.agents/skills`, `~/.config/opencode/skills` → covered by `~/.agents/skills` | one level; bounded by git worktree root |
| Copilot CLI | `AGENTS.md` (root + cwd) by default; also `.github/copilot-instructions.md`, `CLAUDE.md`, `$HOME/.copilot/copilot-instructions.md` | reads `~/.agents/skills` and `~/.copilot/skills` → covered by `~/.agents/skills` | one level; searches repo root + cwd (`COPILOT_CUSTOM_INSTRUCTIONS_DIRS` adds more) |
| VS Code Copilot | `.github/copilot-instructions.md` (default-on); `AGENTS.md` auto-detected at root (toggle `chat.useAgentsMdFile`; nested = experimental `chat.useNestedAgentsMdFiles`) | reads `~/.agents/skills`, `~/.claude/skills`, `~/.copilot/skills` → covered | one level; workspace-root only; skills enabled by default |
| Copilot cloud coding agent | `AGENTS.md` (root + nested) by default; `.github/copilot-instructions.md`, `.github/instructions/**`, `CLAUDE.md`, `GEMINI.md` | in-repo `.github/skills/` (no global dir) | — |

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

def install_skills(env=None, which=shutil.which) -> list[Path]:
    # into each target dir: copy bundled skills + stamp <skill>/.installed-by-odoo-cli;
    # prune marker-bearing folders no longer bundled; skip+warn on a marker-less
    # name collision. Idempotent, so it is also the sync path.
def uninstall_skills(env=None, which=shutil.which) -> list[Path]:
    # remove only marker-bearing folders from the target dirs

def _skill_dirs(env, which) -> set[Path]:
    # ~/.agents/skills always; ~/.claude/skills only if _claude_present
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
  `write_workspace_docs`, `write_worktree_docs`, and `install_skills`, all inside
  one best-effort guard that warns instead of failing `init`.
- `commands/worktree.py` — call `write_worktree_docs` for the new worktree.
- A future `odoo skills` command group (`sync` = `install_skills`, plus
  `uninstall`) can expose the same refresh/removal primitives directly; deferrable
  because re-running `odoo init` already refreshes marker-owned skills.

### Tests

`tests/unit/test_agent_assets.py`, filesystem-only (no process runner):
write-if-absent leaves an existing file untouched; symlink only at the workspace
root; detection matrix via a fake `which` + temp `HOME` (claude →
`~/.claude/skills`; codex-only and opencode-only → `~/.agents/skills`; none →
nothing written); `install_skills` copies skills and stamps the marker, a re-run
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
  dir). Copilot is covered through the shared `AGENTS.md` + `~/.agents/skills`;
  see Non-goals.
- MCP frontend (`requirements_v3.md` → "MCP frontend") — a separate, richer
  integration path; this spec is only about file-based agent context.
- Generating agent context for the `odoo-cli` source repo itself (it already has
  its own `AGENTS.md`).

[Agent Skills]: https://agentskills.io
[openai/codex#6038]: https://github.com/openai/codex/issues/6038
[anomalyco/opencode#2225]: https://github.com/anomalyco/opencode/issues/2225
