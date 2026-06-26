"""Agentic context setup: workspace AGENTS.md files and workspace-local skills.

Plain functions over the markdown shipped under `odoo_cli/agent_assets/` (the
data dir this module is named after). See `specs/agentic_context.md`.

Two artifacts, two lifecycles:

- workspace `AGENTS.md` / `CLAUDE.md` — written create-once, then user-owned;
- skills — copied into the workspace's own skill dirs (tool-owned, refreshed).

Skills install **into the workspace**, not the user's global skill dirs, so they
never bias unrelated (non-Odoo) sessions — a harness preloads every skill's
name+description, so a global install leaks Odoo context everywhere. The cost is
discovery scope: harnesses bound skill search at the git repo root, and a
worktree root is not a git repo, so a harness started there does not auto-load
them (the per-worktree AGENTS.md points at the skill file as a fallback).

Best-effort by contract: callers wrap these in a guard and warn on failure, so
agent setup never fails the host command.
"""

from __future__ import annotations

import importlib.resources as resources
import os
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from odoo_cli.core import paths
from odoo_cli.core.models import Workspace, Worktree

#: Written inside every skill folder we install. The skill dirs may also hold
#: the user's own skills, so refresh/uninstall only ever touch marker-bearing
#: folders; a folder without it is left alone (the `odoo-*` name is namespacing,
#: not ownership).
MARKER = ".installed-by-odoo-cli"

WhichFn = Callable[[str], str | None]


def _assets():
    """The bundled `agent_assets/` as a resources Traversable (not a Path)."""
    return resources.files("odoo_cli") / "agent_assets"


# --- workspace docs (create-once, user-owned) -------------------------------


def write_workspace_docs(
    workspace: Workspace,
    env: Mapping[str, str] | None = None,
    which: WhichFn = shutil.which,
) -> list[Path]:
    """Create the root `AGENTS.md` if absent (always), plus a `CLAUDE.md ->
    AGENTS.md` symlink when Claude is detected. An existing non-empty file of
    either name is left untouched."""
    env = os.environ if env is None else env
    written: list[Path] = []
    agents = workspace.root / "AGENTS.md"
    if _doc_needs_template(agents):
        _write_text(agents, (_assets() / "AGENTS.md").read_text(encoding="utf-8"))
        written.append(agents)
    claude = workspace.root / "CLAUDE.md"
    if (
        _claude_present(env, which)
        and not claude.exists()
        and not claude.is_symlink()
    ):
        os.symlink("AGENTS.md", claude)
        written.append(claude)
    return written


def write_worktree_docs(worktree: Worktree) -> list[Path]:
    """Create the thin per-worktree `AGENTS.md` if absent. No `CLAUDE.md`
    symlink: Claude climbs the tree to the workspace file."""
    agents = worktree.path / "AGENTS.md"
    if not _doc_needs_template(agents):
        return []
    _write_text(
        agents, (_assets() / "AGENTS.worktree.md").read_text(encoding="utf-8")
    )
    return [agents]


def _doc_needs_template(path: Path) -> bool:
    """Absent docs and empty placeholder files get the bundled template.

    Non-empty files are user-owned; symlinks are also left alone, including
    broken ones, because following them could write outside the workspace.
    """
    if path.is_symlink():
        return False
    if not path.exists():
        return True
    return path.is_file() and path.stat().st_size == 0


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# --- skills (tool-owned, refreshable, installed in the workspace) -----------


@dataclass
class SkillsResult:
    installed: list[Path] = field(default_factory=list)
    pruned: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)  # collisions left as-is


def install_skills(
    root: Path,
    env: Mapping[str, str] | None = None,
    which: WhichFn = shutil.which,
) -> SkillsResult:
    """Copy the bundled skills into the workspace's skill dirs (under `root`),
    stamping the ownership MARKER, and prune marker-bearing folders no longer
    bundled.

    A folder without the MARKER is never touched (recorded in `skipped` on a
    name collision). Idempotent, so this is also the refresh/sync path.
    """
    env = os.environ if env is None else env
    result = SkillsResult()
    bundled = _bundled_skills()
    names = {name for name, _ in bundled}
    for skills_dir in _skill_dirs(root, env, which):
        skills_dir.mkdir(parents=True, exist_ok=True)
        for name, src in bundled:
            dest = skills_dir / name
            if dest.exists() and not (dest / MARKER).exists():
                result.skipped.append(dest)
                continue
            if dest.exists():
                shutil.rmtree(dest)
            _copy_tree(src, dest)
            (dest / MARKER).write_text("", encoding="utf-8")
            result.installed.append(dest)
        for child in _subdirs(skills_dir):
            if child.name not in names and (child / MARKER).exists():
                shutil.rmtree(child)
                result.pruned.append(child)
    return result


def uninstall_skills(
    root: Path,
    env: Mapping[str, str] | None = None,
    which: WhichFn = shutil.which,
) -> list[Path]:
    """Remove only marker-bearing skill folders from the workspace skill dirs."""
    env = os.environ if env is None else env
    removed: list[Path] = []
    for skills_dir in _skill_dirs(root, env, which):
        if not skills_dir.is_dir():
            continue
        for child in _subdirs(skills_dir):
            if (child / MARKER).exists():
                shutil.rmtree(child)
                removed.append(child)
    return removed


def prune_legacy_global_skills(env: Mapping[str, str] | None = None) -> list[Path]:
    """Remove marker-bearing skill folders from the **global** `~/.agents/skills`
    and `~/.claude/skills` dirs that earlier versions installed into.

    Skills are now workspace-local; a stale global copy would keep biasing the
    user's unrelated sessions, the very thing the move avoids. Only folders we
    stamped (the MARKER) are removed, so a user's own global skills are safe. The
    Claude dir is swept unconditionally — Claude may since have been removed, but
    our leftovers should still go.
    """
    env = os.environ if env is None else env
    home = Path(env.get("HOME") or Path.home())
    removed: list[Path] = []
    for skills_dir in (home / ".agents" / "skills", home / ".claude" / "skills"):
        if not skills_dir.is_dir():
            continue
        for child in _subdirs(skills_dir):
            if (child / MARKER).exists():
                shutil.rmtree(child)
                removed.append(child)
    return removed


def _bundled_skills() -> list[tuple[str, object]]:
    """`(name, Traversable)` for each bundled skill folder, name-sorted."""
    skills = _assets() / "skills"
    return sorted(
        ((child.name, child) for child in skills.iterdir() if child.is_dir()),
        key=lambda item: item[0],
    )


def _copy_tree(src, dst: Path) -> None:
    """Recursively materialize a resources Traversable onto a real Path.

    Not `shutil.copytree`: on Python 3.10 and for zip/wheel installs the source
    is a Traversable, not a filesystem path.
    """
    dst.mkdir(parents=True, exist_ok=True)
    for child in src.iterdir():
        target = dst / child.name
        if child.is_dir():
            _copy_tree(child, target)
        else:
            target.write_bytes(child.read_bytes())


def _subdirs(path: Path) -> list[Path]:
    # materialized: callers delete entries while iterating
    return [child for child in path.iterdir() if child.is_dir()]


def _skill_dirs(root: Path, env: Mapping[str, str], which: WhichFn) -> set[Path]:
    """`<workspace>/.agents/skills` always — the shared AGENTS.md-convention dir
    read by Codex, opencode, Copilot CLI, and VS Code Copilot; `<workspace>/.claude/skills`
    only when Claude is detected. Both are under the workspace `root`, not the
    user's home, so the skills stay scoped to this workspace."""
    dirs: set[Path] = {root / ".agents" / "skills"}
    if _claude_present(env, which):
        dirs.add(root / ".claude" / "skills")
    return dirs


def _claude_present(env: Mapping[str, str], which: WhichFn) -> bool:
    """Claude Code is available: the `claude` CLI on PATH, its `~/.claude`
    config dir, or a Claude **desktop** app config dir (the desktop app hosts
    Claude Code, which reads the same `~/.claude/skills` and `CLAUDE.md`)."""
    if which("claude") is not None:
        return True
    if paths.claude_dir(env).is_dir():
        return True
    return any(d.is_dir() for d in paths.claude_desktop_dirs(env))
