"""Python virtual environment setup for Odoo."""

import re
import subprocess
from pathlib import Path

from odoo_cli.console import console


def get_min_python_version(directory: Path) -> str | None:
    """Read MIN_PY_VERSION from odoo/release.py and return it as '3.12'."""
    release_py = directory / "odoo" / "odoo" / "release.py"
    if not release_py.exists():
        return None
    content = release_py.read_text()
    match = re.search(r"MIN_PY_VERSION\s*=\s*\((\d+),\s*(\d+)\)", content)
    if not match:
        return None
    return f"{match.group(1)}.{match.group(2)}"


def setup_venv(directory: Path) -> bool:
    """Create or recreate odoo/.venv with Odoo's minimum Python version."""
    python_version = get_min_python_version(directory)
    venv_path = directory / "odoo" / ".venv"

    cmd = ["uv", "venv", str(venv_path)]
    if python_version:
        cmd.extend(["--python", python_version])
        console.print(f"  Setting up venv with Python {python_version}...")
    else:
        console.print("  Setting up venv with system Python...")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        console.print(f"  [red]Failed to create venv:[/red] {result.stderr.strip()}")
        return False

    requirements = directory / "odoo" / "requirements.txt"
    if requirements.exists():
        venv_python = str(venv_path / "bin" / "python")
        console.print("  Installing build dependencies...")
        subprocess.run(
            ["uv", "pip", "install", "--python", venv_python, "setuptools<81", "wheel"],
            capture_output=True,
            text=True,
        )
        console.print("  Installing requirements...")
        result = subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                venv_python,
                "--no-build-isolation",
                "-r",
                str(requirements),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            console.print(f"  [red]Failed to install requirements:[/red] {result.stderr.strip()}")
            return False

    console.print("  [green]venv ready[/green]")
    return True
