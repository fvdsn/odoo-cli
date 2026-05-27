"""Network port helpers."""

import subprocess


def pid_for_port(port: int) -> int | None:
    """Return the first PID listening on a TCP port, if any."""
    result = subprocess.run(
        ["lsof", "-ti", f"tcp:{port}"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return int(result.stdout.strip().splitlines()[0])
    return None
