"""Read facts from a worktree's `odoo/odoo/release.py` without executing it.

The checked-out source is the single source of truth for a worktree's Odoo
version and supported Python range; nothing is stored. Parsing uses `ast`
(release.py mixes literals and names, so no literal_eval of the whole file).
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from pathlib import Path

from odoo_cli.core.errors import InvalidWorkspace


@dataclass(frozen=True)
class ReleaseInfo:
    version: str  # the serie, e.g. "19.0" or "saas~19.4"
    py_min: tuple[int, int] | None
    py_max: tuple[int, int] | None


def normalize_version(version: str) -> str:
    """Filesystem/branch-safe version string: `saas~19.4` -> `saas-19.4`."""
    return version.replace("~", "-")


def read_release(worktree_path: Path) -> ReleaseInfo:
    release_py = worktree_path / "odoo" / "odoo" / "release.py"
    if not release_py.is_file():
        # every version lookup funnels through here, so this is the one
        # place that can name the real problem of a dead linked worktree
        odoo_entry = worktree_path / "odoo"
        if odoo_entry.is_symlink() and not odoo_entry.exists():
            source = Path(os.readlink(odoo_entry)).parent.name
            raise InvalidWorkspace(
                f"'{worktree_path.name}' is a linked worktree, but its "
                f"source worktree '{source}' no longer exists",
                hint=(
                    f"recreate the source (`odoo worktree create {source}`) "
                    f"or remove {worktree_path}"
                ),
            )
        raise InvalidWorkspace(
            f"{release_py} not found; is this a valid Odoo worktree?"
        )
    assignments = _module_assignments(release_py)

    version_info = assignments.get("version_info")
    if not isinstance(version_info, tuple) or len(version_info) < 2:
        raise InvalidWorkspace(f"could not parse version_info in {release_py}")
    major, minor = version_info[0], version_info[1]
    version = f"{major}.{minor}"

    return ReleaseInfo(
        version=version,
        py_min=_py_tuple(assignments.get("MIN_PY_VERSION")),
        py_max=_py_tuple(assignments.get("MAX_PY_VERSION")),
    )


def _module_assignments(path: Path) -> dict[str, object]:
    """Top-level `NAME = <expr>` assignments, best-effort evaluated: literal
    elements are kept, non-literal ones (e.g. the FINAL name in version_info)
    are dropped from tuples."""
    tree = ast.parse(path.read_text())
    values: dict[str, object] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        values[target.id] = _best_effort_value(node.value)
    return values


def _best_effort_value(node: ast.expr) -> object:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Tuple):
        return tuple(
            elt.value for elt in node.elts if isinstance(elt, ast.Constant)
        )
    return None


def _py_tuple(value: object) -> tuple[int, int] | None:
    if (
        isinstance(value, tuple)
        and len(value) >= 2
        and all(isinstance(v, int) for v in value[:2])
    ):
        return (value[0], value[1])
    return None
