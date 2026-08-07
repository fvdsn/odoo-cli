"""External python dependencies declared in module manifests.

Odoo's requirements.txt deliberately omits some packages that modules
declare via `external_dependencies.python` (phonenumbers, …); odoo-bin
refuses to load such a module when the package is missing. The rule is
uniform: any command about to load modules (test, module install/update,
db reset, start, shell) runs `ensure_module_deps` over the modules that
run will load, so the failure is fixed — or explained — before odoo-bin.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import TYPE_CHECKING

from odoo_cli.core.addons import resolve_addons_paths
from odoo_cli.core.errors import ExternalDependencyNotInstallable
from odoo_cli.core.models import Worktree
from odoo_cli.util.process import ProcessError, ProcessRunner

if TYPE_CHECKING:  # venvs.py imports this module; annotate without a cycle
    from odoo_cli.core.venvs import VenvService

#: leading distribution name of a requirement string ("phonenumbers>=8" -> name)
_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+")


def python_deps(
    worktree: Worktree, modules: list[str] | None
) -> dict[str, list[str]]:
    """{distribution name: [modules that need it]} read from the manifests'
    external_dependencies.python; `modules=None` scans every module in the
    worktree's addons paths (venv builds derive the full set from disk)."""
    wanted = None if modules is None else set(modules)
    deps: dict[str, list[str]] = {}
    for path in resolve_addons_paths(worktree):
        if not path.is_dir():
            continue
        for child in path.iterdir():
            if wanted is not None and child.name not in wanted:
                continue
            for requirement in _manifest_python_deps(child / "__manifest__.py"):
                match = _NAME_RE.match(requirement.strip())
                if match:
                    deps.setdefault(match.group(0), []).append(child.name)
    return {name: sorted(mods) for name, mods in deps.items()}


def _manifest_python_deps(manifest: Path) -> list[str]:
    try:
        data = ast.literal_eval(manifest.read_text())
    except (OSError, ValueError, SyntaxError):
        return []
    external = data.get("external_dependencies") if isinstance(data, dict) else None
    python = external.get("python") if isinstance(external, dict) else None
    return [d for d in (python or []) if isinstance(d, str)]


#: the same check odoo-bin performs (importlib.metadata, not import), run
#: inside the venv's interpreter — odoo-cli's own environment is irrelevant
_PROBE = (
    "import importlib.metadata, sys\n"
    "for name in sys.argv[1:]:\n"
    "    try:\n"
    "        importlib.metadata.version(name)\n"
    "    except importlib.metadata.PackageNotFoundError:\n"
    "        print(name)\n"
)


def missing_distributions(
    runner: ProcessRunner, python: Path, names: list[str]
) -> list[str]:
    """The distributions among `names` without metadata in the venv."""
    if not names:
        return []
    result = runner.run([python, "-c", _PROBE, *sorted(names)])
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def ensure_module_deps(
    venvs: VenvService,
    runner: ProcessRunner,
    worktree: Worktree,
    modules: list[str],
    venv: Path,
    python: Path,
) -> None:
    """Make `modules`' manifest-declared python deps importable in the venv:
    probe, auto-install what is missing, and raise a typed error when the
    install fails."""
    deps = python_deps(worktree, modules)
    missing = missing_distributions(runner, python, list(deps))
    if not missing:
        return
    try:
        venvs.install_packages(venv, missing)
    except ProcessError as exc:
        needed = ", ".join(
            f"{name} (needed by {', '.join(deps[name])})" for name in sorted(missing)
        )
        raise ExternalDependencyNotInstallable(
            f"could not install external dependencies: {needed}",
            hint=(
                f"install manually with `{python} -m pip install "
                f"{' '.join(sorted(missing))}`"
            ),
        ) from exc
