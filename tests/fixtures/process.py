"""Fake process runner for unit tests.

Scripted by command prefix: register results with `expect()`; every executed
command is recorded in `calls` for assertions. Unexpected commands fail the
test immediately, so a service can never silently shell out.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from odoo_cli.util.process import ProcessError, ProcessResult


def createdb_call(name: str) -> tuple[str, ...]:
    """The exact argv `PostgresService.create_db` runs: odoo's own creation
    semantics (encoding, C collation, template0)."""
    return (
        "createdb", "--encoding=UTF8", "--lc-collate=C",
        "--template=template0", name,
    )


class FakeProcessRunner:
    def __init__(self):
        self.calls: list[tuple[str, ...]] = []
        self.stream_calls: list[tuple[str, ...]] = []
        self._scripts: list[
            tuple[tuple[str, ...], ProcessResult, Callable | None]
        ] = []
        self._stream_scripts: list[
            tuple[tuple[str, ...], int, Callable | None]
        ] = []
        self.stream_returncode = 0

    def expect(
        self,
        *prefix: str,
        stdout: str = "",
        stderr: str = "",
        returncode: int = 0,
        effect: Callable[[tuple[str, ...]], None] | None = None,
    ) -> None:
        """Make any command starting with `prefix` return this result.

        Later registrations win over earlier ones, so tests can override a
        broad default with a specific case. `effect(argv)` runs on match to
        emulate filesystem side effects (clones creating directories, ...).
        """
        result = ProcessResult(
            argv=prefix, returncode=returncode, stdout=stdout, stderr=stderr
        )
        self._scripts.insert(0, (prefix, result, effect))

    def expect_stream(
        self,
        *prefix: str,
        returncode: int = 0,
        effect: Callable[[tuple[str, ...]], None] | None = None,
    ) -> None:
        self._stream_scripts.insert(0, (prefix, returncode, effect))

    def run(
        self,
        argv: list[str | Path],
        *,
        cwd: Path | None = None,
        extra_env: dict[str, str] | None = None,
        check: bool = True,
        input: str | None = None,
    ) -> ProcessResult:
        call = tuple(str(a) for a in argv)
        self.calls.append(call)
        for prefix, scripted, effect in self._scripts:
            if call[: len(prefix)] == prefix:
                if effect is not None:
                    effect(call)
                result = ProcessResult(
                    argv=call,
                    returncode=scripted.returncode,
                    stdout=scripted.stdout,
                    stderr=scripted.stderr,
                )
                if check and result.returncode != 0:
                    raise ProcessError(result)
                return result
        raise AssertionError(f"unexpected subprocess: {' '.join(call)}")

    def stream(
        self,
        argv: list[str | Path],
        *,
        cwd: Path | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> int:
        call = tuple(str(a) for a in argv)
        self.stream_calls.append(call)
        for prefix, returncode, effect in self._stream_scripts:
            if call[: len(prefix)] == prefix:
                if effect is not None:
                    effect(call)
                return returncode
        return self.stream_returncode
