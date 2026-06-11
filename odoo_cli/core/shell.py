"""`odoo shell`: interactive REPL or one-shot code execution."""

from __future__ import annotations

from odoo_cli.core.database import DatabaseService
from odoo_cli.core.errors import ProcessFailed
from odoo_cli.core.models import Target
from odoo_cli.core.odoo_bin import OdooBinService
from odoo_cli.core.venvs import VenvService
from odoo_cli.util.process import ProcessRunner


class ShellService:
    def __init__(
        self,
        database: DatabaseService,
        odoo_bin: OdooBinService,
        venvs: VenvService,
        runner: ProcessRunner,
    ):
        self.database = database
        self.odoo_bin = odoo_bin
        self.venvs = venvs
        self.runner = runner

    def interactive(self, target: Target) -> int:
        command = self._command(target)
        return self.runner.stream(
            command.argv, cwd=command.cwd, extra_env=command.env
        )

    def execute(self, target: Target, code: str) -> str:
        """Run CODE in the Odoo environment, return its stdout."""
        command = self._command(target)
        result = self.runner.run(
            command.argv, cwd=command.cwd, extra_env=command.env,
            input=code, check=False,
        )
        if result.returncode != 0:
            raise ProcessFailed(
                f"shell exited {result.returncode}",
                argv=command.redacted_argv,
                returncode=result.returncode,
                stderr=result.stderr,
            )
        return result.stdout

    def _command(self, target: Target):
        venv = self.venvs.ensure(target.workspace, target.worktree)
        python = self.venvs.python_path(venv.path)
        self.database.ensure_initialized(target, python=python)
        return self.odoo_bin.shell(target, python=python)
