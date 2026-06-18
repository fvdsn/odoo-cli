"""Agentic context setup: workspace AGENTS.md files and global skill install.

Plain functions over the markdown shipped under `odoo_cli/agent_assets/` (the
data dir this module is named after). See `specs/agentic_context.md`.

Two artifacts, two lifecycles:

- workspace `AGENTS.md` / `CLAUDE.md` — written create-once, then user-owned;
- skills — copied into the harnesses' global skill dirs (tool-owned, refreshed).

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

#: Written inside every skill folder we install. The global skill dirs are
#: shared with the user, so refresh/uninstall only ever touch marker-bearing
#: folders; a folder without it is left alone (the `odoo-*` name is namespacing,
#: not ownership).
MARKER = ".installed-by-odoo-cli"

WhichFn = Callable[[str], str | None]


def _assets():
    """The bundled `agent_assets/` as a resources Traversable (not a Path)."""
    return resources.files("odoo_cli") / "agent_assets"


# --- workspace docs (create-once, user-owned) -------------------------------


def write_workspace_docs(workspace: Workspace) -> list[Path]:
    """Create the root `AGENTS.md` (+ `CLAUDE.md` symlink) if absent. An
    existing non-empty file of either name is left untouched."""
    written: list[Path] = []
    agents = workspace.root / "AGENTS.md"
    if _doc_needs_template(agents):
        _write_text(agents, (_assets() / "AGENTS.md").read_text(encoding="utf-8"))
        written.append(agents)
    claude = workspace.root / "CLAUDE.md"
    if not claude.exists() and not claude.is_symlink():
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


# --- skills (tool-owned, refreshable, installed globally) -------------------


@dataclass
class SkillsResult:
    installed: list[Path] = field(default_factory=list)
    pruned: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)  # collisions left as-is


def install_skills(
    env: Mapping[str, str] | None = None, which: WhichFn = shutil.which
) -> SkillsResult:
    """Copy the bundled skills into each detected harness skill dir, stamping
    the ownership MARKER, and prune marker-bearing folders no longer bundled.

    A folder without the MARKER is never touched (recorded in `skipped` on a
    name collision). Idempotent, so this is also the refresh/sync path.
    """
    env = os.environ if env is None else env
    result = SkillsResult()
    bundled = _bundled_skills()
    names = {name for name, _ in bundled}
    for skills_dir in _skill_dirs(env, which):
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
    env: Mapping[str, str] | None = None, which: WhichFn = shutil.which
) -> list[Path]:
    """Remove only marker-bearing skill folders from the detected dirs."""
    env = os.environ if env is None else env
    removed: list[Path] = []
    for skills_dir in _skill_dirs(env, which):
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


def _skill_dirs(env: Mapping[str, str], which: WhichFn) -> set[Path]:
    """Detected harness skill dirs: `~/.claude/skills` if Claude is present;
    `~/.agents/skills` if Codex or opencode is present (opencode reads it too).
    """
    dirs: set[Path] = set()
    if _present("claude", paths.claude_dir(env), which):
        dirs.add(paths.claude_skills_dir(env))
    if _present("codex", paths.codex_dir(env), which) or _present(
        "opencode", paths.opencode_dir(env), which
    ):
        dirs.add(paths.agents_skills_dir(env))
    return dirs


def _present(cli: str, config_dir: Path, which: WhichFn) -> bool:
    return which(cli) is not None or config_dir.is_dir()
