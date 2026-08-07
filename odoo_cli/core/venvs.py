"""Venv management: one venv per detected Odoo version, shared by worktrees.

The CLI's own interpreter and the venv interpreter are separate problems: the
supported range comes from the worktree's release.py (MIN/MAX_PY_VERSION) and
a compatible interpreter is looked up on PATH — never assume the interpreter
running the CLI suits Odoo. uv creates the venv when available (and can
provision a missing interpreter); the fallback is `pythonX.Y -m venv` + pip.

A venv is trusted only once its ready-marker exists, so a creation that died
mid-`pip install` is retried instead of silently reused.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from odoo_cli.core import external_deps, release
from odoo_cli.core.errors import NoCompatiblePython
from odoo_cli.core.models import Workspace, Worktree
from odoo_cli.util.locks import file_lock
from odoo_cli.util.process import ProcessRunner

READY_MARKER = ".odoo-cli-ready"


@dataclass
class VenvResult:
    path: Path
    created: bool


class VenvService:
    def __init__(
        self,
        runner: ProcessRunner,
        which: Callable[[str], str | None] = shutil.which,
    ):
        self.runner = runner
        self.which = which

    def venv_path(self, workspace: Workspace, worktree: Worktree) -> Path:
        info = release.read_release(worktree.path)
        return workspace.venvs_dir / release.normalize_version(info.version)

    def python_path(self, venv: Path) -> Path:
        return venv / "bin" / "python"

    def ensure(self, workspace: Workspace, worktree: Worktree) -> VenvResult:
        """Create the resolved venv if needed. Called by every command that
        runs odoo-bin (a pull can retarget the venv, e.g. master rolling
        forward)."""
        path = self.venv_path(workspace, worktree)
        if self._ready(path):
            return VenvResult(path=path, created=False)
        with file_lock(self._lock_path(path)):
            if self._ready(path):
                # another process built it while we waited for the lock
                return VenvResult(path=path, created=False)
            # incomplete (no ready marker): a failed creation may have left
            # stale state behind; recreate from scratch
            self._remove(path)
            self._create(path, worktree)
        return VenvResult(path=path, created=True)

    def rebuild(self, workspace: Workspace, worktree: Worktree) -> VenvResult:
        """`odoo venv`: recreate from scratch."""
        path = self.venv_path(workspace, worktree)
        with file_lock(self._lock_path(path)):
            self._remove(path)
            self._create(path, worktree)
        return VenvResult(path=path, created=True)

    def _ready(self, path: Path) -> bool:
        return (path / READY_MARKER).is_file() and self.python_path(path).exists()

    @staticmethod
    def _lock_path(path: Path) -> Path:
        return path.parent / f".{path.name}.lock"

    @staticmethod
    def _remove(path: Path) -> None:
        """Remove whatever sits at the venv path: a directory, or — after
        manual tampering — a file or symlink (deleted, never followed)."""
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        elif path.exists() or path.is_symlink():
            path.unlink()

    def _create(self, path: Path, worktree: Worktree) -> None:
        info = release.read_release(worktree.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        uv = self.which("uv")
        interpreter = self._find_interpreter(info)
        if uv:
            self.runner.run(
                ["uv", "venv", "--python", interpreter or self._uv_spec(info), path]
            )
        elif interpreter:
            self.runner.run([interpreter, "-m", "venv", str(path)])
        else:
            raise NoCompatiblePython(
                f"no Python in {self._range_text(info)} found for Odoo "
                f"{info.version}",
                hint=(
                    "install a compatible python (apt/brew install "
                    f"python{self._preferred(info)}) or install uv, which can "
                    "provision one (https://docs.astral.sh/uv/)"
                ),
            )
        self._install_requirements(path, worktree, uv)
        self._install_manifest_deps(path, worktree)
        path.mkdir(parents=True, exist_ok=True)  # no-op after a real create
        (path / READY_MARKER).touch()

    def _install_manifest_deps(self, path: Path, worktree: Worktree) -> None:
        """Manifest external_dependencies.python beyond requirements.txt
        (phonenumbers, …), derived from the worktree's addons on every
        (re)build — the manifests are the record, nothing is persisted.
        Best-effort: one exotic module's uninstallable dep must not block the
        venv; commands that actually select such a module raise the typed
        error at their own pre-flight."""
        from odoo_cli.util.process import ProcessError

        deps = external_deps.python_deps(worktree, None)
        python = self.python_path(path)
        try:
            missing = external_deps.missing_distributions(self.runner, python, list(deps))
            if missing:
                self.install_packages(path, missing)
        except ProcessError:
            pass

    def install_packages(self, venv: Path, packages: list[str]) -> None:
        """Install extra distributions into an existing venv (manifest
        external_dependencies beyond requirements.txt)."""
        python = self.python_path(venv)
        if self.which("uv"):
            self.runner.run(["uv", "pip", "install", "--python", python, *packages])
        else:
            self.runner.run([python, "-m", "pip", "install", *packages])

    def _install_requirements(self, path: Path, worktree: Worktree, uv: str | None) -> None:
        requirements = worktree.path / "odoo" / "requirements.txt"
        if not requirements.is_file():
            return
        python = self.python_path(path)
        if uv:
            self.runner.run(
                ["uv", "pip", "install", "--python", python, "-r", requirements]
            )
        else:
            self.runner.run([python, "-m", "pip", "install", "-r", requirements])

    def _find_interpreter(self, info: release.ReleaseInfo) -> str | None:
        """Highest `pythonX.Y` on PATH within [MIN_PY_VERSION, MAX_PY_VERSION]."""
        for minor in self._minor_range(info):
            found = self.which(f"python3.{minor}")
            if found:
                return found
        return None

    def _minor_range(self, info: release.ReleaseInfo) -> list[int]:
        low = info.py_min[1] if info.py_min else 10
        high = info.py_max[1] if info.py_max else low + 4
        return list(range(high, low - 1, -1))

    def _preferred(self, info: release.ReleaseInfo) -> str:
        return f"3.{self._minor_range(info)[0]}"

    def _uv_spec(self, info: release.ReleaseInfo) -> str:
        """Version request letting uv provision a missing interpreter."""
        low = info.py_min[1] if info.py_min else 10
        spec = f">=3.{low}"
        if info.py_max:
            spec += f",<3.{info.py_max[1] + 1}"
        return spec

    def _range_text(self, info: release.ReleaseInfo) -> str:
        low = f"3.{info.py_min[1]}" if info.py_min else "3.10"
        high = f"3.{info.py_max[1]}" if info.py_max else "?"
        return f"[{low}, {high}]"
