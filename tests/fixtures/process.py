"""Fake process runner for unit tests.

Scripted by command prefix: register results with `expect()`; every executed
command is recorded in `calls` for assertions. Unexpected commands fail the
test immediately, so a service can never silently shell out.
"""

from __future__ import annotations

from pathlib import Path

from odoo_cli.util.process import ProcessError, ProcessResult


class FakeProcessRunner:
    def __init__(self):
        self.calls: list[tuple[str, ...]] = []
        self.stream_calls: list[tuple[str, ...]] = []
        self._scripts: list[tuple[tuple[str, ...], ProcessResult]] = []
        self.stream_returncode = 0

    def expect(
        self,
        *prefix: str,
        stdout: str = "",
        stderr: str = "",
        returncode: int = 0,
    ) -> None:
        """Make any command starting with `prefix` return this result.

        Later registrations win over earlier ones, so tests can override a
        broad default with a specific case.
        """
        result = ProcessResult(
            argv=prefix, returncode=returncode, stdout=stdout, stderr=stderr
        )
        self._scripts.insert(0, (prefix, result))

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
        for prefix, scripted in self._scripts:
            if call[: len(prefix)] == prefix:
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
        self.stream_calls.append(tuple(str(a) for a in argv))
        return self.stream_returncode
