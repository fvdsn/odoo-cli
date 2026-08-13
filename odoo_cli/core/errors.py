"""Typed errors raised by core services.

The CLI layer translates these into concise messages and exit codes
(0 success, 1 user-facing failure, 2 usage error). `hint` carries an
optional one-line next action shown after the message.
"""

import re


class OdooCliError(Exception):
    """Base class for user-facing failures (exit code 1)."""

    def __init__(self, message: str, *, hint: str | None = None):
        super().__init__(message)
        self.message = message
        self.hint = hint

    @property
    def code(self) -> str:
        """Stable machine-readable identifier, derived from the class name
        (WorktreeNotFound -> worktree_not_found). Part of the JSON error
        contract: renaming an exception class is a breaking change."""
        return re.sub(r"(?<!^)(?=[A-Z])", "_", type(self).__name__).lower()


class WorkspaceNotFound(OdooCliError):
    """No workspace at the resolved location (missing .repositories/odoo.git)."""


class InvalidWorkspace(OdooCliError):
    """A workspace exists but is broken or incomplete."""


class TargetAmbiguous(OdooCliError):
    """Multiple worktrees exist and none was selected."""


class WorktreeNotFound(OdooCliError):
    pass


class WorktreeExists(OdooCliError):
    pass


class WorktreeRemovalBlocked(OdooCliError):
    """A removal was refused by a safety check (uncommitted changes, unmerged
    branches, a live server, or linked dependents)."""


class InvalidName(OdooCliError):
    """A worktree, repository, or database name breaks the shared name rules."""


class RepositoryNotFound(OdooCliError):
    pass


class RepositoryExists(OdooCliError):
    pass


class RepositoryHasNoRemote(OdooCliError):
    """The bare repo has no `origin` remote; operations that fetch need one."""


class VersionNotFound(OdooCliError):
    """The requested Odoo version/ref does not exist in a repository."""


class UnsupportedOdooVersion(OdooCliError):
    """The detected Odoo version is older than what the CLI supports."""


class NoCompatiblePython(OdooCliError):
    """No interpreter satisfies the worktree's MIN/MAX_PY_VERSION range."""


class PortUnavailable(OdooCliError):
    """The instance's reserved port is taken by another process."""


class PostgresError(OdooCliError):
    pass


class ReportDepsError(OdooCliError):
    """A report-rendering system dependency (wkhtmltopdf, cairo) could not
    be installed."""


class DatabaseNotFound(OdooCliError):
    """Read-only command targeting a database that does not exist."""


class DatabaseExists(OdooCliError):
    """Clone/rename target database already exists."""


class ExternalDependencyNotInstallable(OdooCliError):
    """A manifest-declared python dependency could not be installed into the
    venv; the hint offers manual install and --skip-missing-deps."""


class ServerNotRunning(OdooCliError):
    pass


class StreamedProcessExit(Exception):
    """A terminal-attached subprocess (server, shell) exited non-zero.

    Not an OdooCliError: the child already wrote its own output, so the CLI
    propagates the exit code without printing anything. Command adapters
    raise this instead of calling sys.exit; cli.main translates it.
    """

    def __init__(self, code: int):
        super().__init__(f"streamed process exited {code}")
        self.code = code


class ProcessFailed(OdooCliError):
    """A subprocess exited non-zero where success was required."""

    def __init__(
        self,
        message: str,
        *,
        argv: list[str] | None = None,
        returncode: int | None = None,
        stderr: str | None = None,
        hint: str | None = None,
    ):
        super().__init__(message, hint=hint)
        self.argv = argv or []
        self.returncode = returncode
        self.stderr = stderr
