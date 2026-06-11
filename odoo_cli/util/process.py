"""Injectable subprocess runner — the v1 test seam.

All subprocess execution (git, psql, venv tooling, odoo-bin) goes through a
`ProcessRunner` instance so tests can substitute a fake. Failures raise
`ProcessError`, which services translate into typed core errors.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProcessResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class ProcessError(Exception):
    """A subprocess exited non-zero where success was required."""

    def __init__(self, result: ProcessResult):
        self.result = result
        super().__init__(
            f"command failed with exit code {result.returncode}: {' '.join(result.argv)}"
        )


def _merged_env(extra_env: dict[str, str] | None) -> dict[str, str] | None:
    if extra_env is None:
        return None
    return {**os.environ, **extra_env}


class ProcessRunner:
    """Runs subprocesses. Inject a fake (tests/fixtures) to avoid real ones."""

    def run(
        self,
        argv: list[str | Path],
        *,
        cwd: Path | None = None,
        extra_env: dict[str, str] | None = None,
        check: bool = True,
        input: str | None = None,
    ) -> ProcessResult:
        """Run with captured output; for queries and non-interactive work."""
        proc = subprocess.run(
            [str(a) for a in argv],
            cwd=cwd,
            env=_merged_env(extra_env),
            capture_output=True,
            text=True,
            input=input,
        )
        result = ProcessResult(
            argv=tuple(str(a) for a in argv),
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )
        if check and result.returncode != 0:
            raise ProcessError(result)
        return result

    def stream(
        self,
        argv: list[str | Path],
        *,
        cwd: Path | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> int:
        """Run attached to the terminal (foreground server, interactive
        shells). Returns the exit code; never raises on non-zero."""
        return subprocess.call(
            [str(a) for a in argv],
            cwd=cwd,
            env=_merged_env(extra_env),
        )
