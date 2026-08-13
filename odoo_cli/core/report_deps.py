"""Report-rendering system dependencies: wkhtmltopdf and cairo.

Reports need a PDF engine; odoo-bin's default is wkhtmltopdf (the
`base_report_wkhtmltox` module is auto-installed and looks the binary up on
PATH). The wkhtmltopdf project is discontinued and gone from Homebrew, so
macOS installs the last official .pkg from the wkhtmltopdf/packaging GitHub
releases — an x86_64 build that runs through Rosetta 2 on Apple Silicon.
Linux installs the distro package via apt.

Barcode/QR rendering (invoice QR codes, receipts) goes through reportlab
4.x, whose PNG backend rlPyCairo builds pycairo from source: pycairo ships
no macOS/Linux wheels, so the cairo library and pkg-config must be present
before the venv installs it (see VenvService).
"""

from __future__ import annotations

import os
import shlex
import shutil
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from odoo_cli.core.errors import ReportDepsError
from odoo_cli.util.process import ProcessRunner

#: Last official macOS build (2020, x86_64); the project ships no newer one.
MACOS_PKG_URL = (
    "https://github.com/wkhtmltopdf/packaging/releases/download/"
    "0.12.6-2/wkhtmltox-0.12.6-2.macos-cocoa.pkg"
)


@dataclass(frozen=True)
class DepInstallPlan:
    manager: str
    commands: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class DepInstallResult:
    manager: str
    warnings: tuple[str, ...] = ()


class ReportDepsService:
    def __init__(
        self,
        runner: ProcessRunner,
        which: Callable[[str], str | None] = shutil.which,
        *,
        platform: str | None = None,
        geteuid: Callable[[], int | None] | None = None,
        download_dir: Path | None = None,
    ):
        self.runner = runner
        self.which = which
        self.platform = sys.platform if platform is None else platform
        self.geteuid = (
            getattr(os, "geteuid", lambda: None) if geteuid is None else geteuid
        )
        self.download_dir = (
            Path(tempfile.gettempdir()) if download_dir is None else download_dir
        )

    # -- wkhtmltopdf (PDF engine) ------------------------------------------

    def wkhtmltopdf_installed(self) -> bool:
        return self.which("wkhtmltopdf") is not None

    def wkhtmltopdf_plan(self) -> DepInstallPlan:
        if self.platform == "darwin":
            pkg = self.download_dir / MACOS_PKG_URL.rsplit("/", 1)[1]
            return DepInstallPlan(
                manager="the official macOS package",
                commands=(
                    ("curl", "-fL", "-o", str(pkg), MACOS_PKG_URL),
                    self._admin_prefix("wkhtmltopdf")
                    + ("installer", "-pkg", str(pkg), "-target", "/"),
                ),
            )
        if self.platform.startswith("linux"):
            return DepInstallPlan(
                manager="apt-get",
                commands=(
                    self._apt("wkhtmltopdf") + ("update",),
                    self._apt("wkhtmltopdf") + ("install", "-y", "wkhtmltopdf"),
                ),
            )
        raise ReportDepsError(
            f"wkhtmltopdf is not installed on unsupported platform "
            f"{self.platform!r}",
            hint="install wkhtmltopdf manually, then re-run `odoo init`",
        )

    def install_wkhtmltopdf(self) -> DepInstallResult:
        """Install wkhtmltopdf. Output streams directly to the terminal:
        the download is long-running and sudo may prompt for a password."""
        plan = self.wkhtmltopdf_plan()
        self._run_plan(plan, "wkhtmltopdf")
        if not self.wkhtmltopdf_installed():
            raise ReportDepsError(
                "wkhtmltopdf installation finished but the binary was not found",
                hint="make sure its location is on PATH, then re-run `odoo init`",
            )
        warnings = []
        probe = self.runner.run(["wkhtmltopdf", "--version"], check=False)
        if probe.returncode != 0:
            # the macOS build is x86_64-only; a fresh Apple Silicon machine
            # needs Rosetta 2 before the binary runs
            warnings.append(
                "wkhtmltopdf is installed but does not run; on Apple Silicon "
                "install Rosetta 2 first: "
                "softwareupdate --install-rosetta --agree-to-license"
            )
        return DepInstallResult(manager=plan.manager, warnings=tuple(warnings))

    # -- cairo (barcode/QR rendering) --------------------------------------

    def cairo_installed(self) -> bool:
        """pkg-config finding cairo is exactly what the pycairo build needs."""
        if not self.which("pkg-config"):
            return False
        probe = self.runner.run(["pkg-config", "--exists", "cairo"], check=False)
        return probe.returncode == 0

    def cairo_plan(self) -> DepInstallPlan:
        if self.platform == "darwin":
            if not self.which("brew"):
                raise ReportDepsError(
                    "cairo is not installed and Homebrew was not found",
                    hint=(
                        "install Homebrew or cairo manually, then re-run "
                        "`odoo init`"
                    ),
                )
            return DepInstallPlan(
                manager="Homebrew",
                commands=(("brew", "install", "cairo", "pkg-config"),),
            )
        if self.platform.startswith("linux"):
            return DepInstallPlan(
                manager="apt-get",
                commands=(
                    self._apt("cairo") + ("update",),
                    self._apt("cairo")
                    + ("install", "-y", "libcairo2-dev", "pkg-config"),
                ),
            )
        raise ReportDepsError(
            f"cairo is not installed on unsupported platform {self.platform!r}",
            hint="install cairo manually, then re-run `odoo init`",
        )

    def install_cairo(self) -> DepInstallResult:
        plan = self.cairo_plan()
        self._run_plan(plan, "cairo")
        if not self.cairo_installed():
            raise ReportDepsError(
                "cairo installation finished but pkg-config does not find it",
                hint="check the cairo install, then re-run `odoo init`",
            )
        return DepInstallResult(manager=plan.manager)

    # -- shared -------------------------------------------------------------

    def _run_plan(self, plan: DepInstallPlan, dep: str) -> None:
        for command in plan.commands:
            code = self.runner.stream(list(command))
            if code != 0:
                raise ReportDepsError(
                    f"could not install {dep}",
                    hint=f"failed command: {shlex.join(command)}",
                )

    def _apt(self, dep: str) -> tuple[str, ...]:
        if not self.which("apt-get"):
            raise ReportDepsError(
                f"{dep} is not installed and apt-get was not found",
                hint=(
                    f"install {dep} with your system package manager, "
                    "then re-run `odoo init`"
                ),
            )
        return self._admin_prefix(dep) + (
            "env", "DEBIAN_FRONTEND=noninteractive", "apt-get",
        )

    def _admin_prefix(self, dep: str) -> tuple[str, ...]:
        if self.geteuid() == 0:
            return ()
        if self.which("sudo"):
            return ("sudo",)
        raise ReportDepsError(
            f"{dep} is not installed and administrator privileges are needed",
            hint="run `odoo init` as root or install sudo, then try again",
        )
