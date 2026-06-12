"""Run-state store and server lifecycle (v1: foreground only).

Port rules (docs/requirements.md → "Port management"): ports are stable per
(worktree, db) via `.run/{worktree}/{db}/ports`, never reassigned silently.
Allocation picks the smallest free port >= base, http and gevent share one
reservation pool, availability is verified by binding, the reservation is
written before the final bind check so concurrent starts see each other, and
a newly created reservation rolls back when that final check fails.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from pathlib import Path

from odoo_cli.core.errors import PortUnavailable
from odoo_cli.core.models import Ports, Target, Workspace
from odoo_cli.util import net
from odoo_cli.util.process import ProcessRunner

DEFAULT_HTTP_PORT = 8069
DEFAULT_GEVENT_PORT = 8072


class RunStateStore:
    """Reads/writes `.run/{worktree}/{db}/` files. v1 only knows `ports`.
    Everything here is ephemeral and safe to delete."""

    def run_dir(self, target: Target) -> Path:
        return target.workspace.run_dir / target.worktree.name / target.database

    def read_ports(self, target: Target) -> Ports | None:
        return self._parse(self.run_dir(target) / "ports")

    def write_ports(self, target: Target, ports: Ports) -> None:
        """Atomic write: unique temp file + rename (a fixed temp name would
        let two concurrent starts interleave write and rename)."""
        run_dir = self.run_dir(target)
        run_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=run_dir, prefix=".ports.")
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(f"http={ports.http}\ngevent={ports.gevent}\n")
            os.replace(tmp, run_dir / "ports")
        except BaseException:
            os.unlink(tmp)
            raise

    def delete_ports(self, target: Target) -> None:
        (self.run_dir(target) / "ports").unlink(missing_ok=True)

    def reserved_ports(self, workspace: Workspace, exclude: Target | None = None) -> set[int]:
        """Every port reserved by any instance's `ports` file. Reservations
        of worktrees that no longer exist on disk do not count."""
        reserved: set[int] = set()
        run_root = workspace.run_dir
        if not run_root.is_dir():
            return reserved
        exclude_file = (
            self.run_dir(exclude) / "ports" if exclude is not None else None
        )
        for ports_file in run_root.glob("*/*/ports"):
            worktree_name = ports_file.parent.parent.name
            if not (workspace.root / worktree_name / "odoo").exists():
                continue  # stale: the worktree is gone
            if exclude_file is not None and ports_file == exclude_file:
                continue
            ports = self._parse(ports_file)
            if ports:
                reserved.update(ports.all())
        return reserved

    def _parse(self, path: Path) -> Ports | None:
        if not path.is_file():
            return None
        values: dict[str, int] = {}
        for line in path.read_text().splitlines():
            key, _, value = line.partition("=")
            if value.strip().isdigit():
                values[key.strip()] = int(value.strip())
        if "http" not in values or "gevent" not in values:
            return None
        return Ports(http=values["http"], gevent=values["gevent"])


class ServerService:
    def __init__(
        self,
        store: RunStateStore,
        runner: ProcessRunner,
        port_free: Callable[[int], bool] = net.port_free,
        http_probe: Callable[[int], str | None] = net.http_probe,
    ):
        self.store = store
        self.runner = runner
        self.port_free = port_free
        self.http_probe = http_probe

    # -- port allocation ----------------------------------------------------

    def allocate_ports(self, target: Target, *, new_port: bool = False) -> Ports:
        existing = self.store.read_ports(target)
        if existing and not new_port:
            busy = [p for p in existing.all() if not self.port_free(p)]
            if not busy:
                return existing
            raise PortUnavailable(
                f"port {busy[0]} (reserved for {target.worktree.name}/"
                f"{target.database}) is taken: {self._diagnose(busy[0])}",
                hint="use `odoo start --new-port` to allocate a different port",
            )
        return self._allocate_fresh(target, previous=existing)

    def preview_ports(self, target: Target) -> Ports:
        """The ports a start would likely use, without reserving anything.

        Unreserved candidates are an estimate: no bind check happens here
        (`odoo where` must not touch sockets), so a foreign process squatting
        a candidate port makes the real allocation pick the next one."""
        existing = self.store.read_ports(target)
        if existing:
            return existing
        reserved = self.store.reserved_ports(target.workspace, exclude=target)
        http_base, gevent_base = self._bases(target)
        http = self._smallest_free(http_base, reserved, check_bind=False)
        gevent = self._smallest_free(
            gevent_base, reserved | {http}, check_bind=False
        )
        return Ports(http=http, gevent=gevent)

    def _allocate_fresh(self, target: Target, previous: Ports | None) -> Ports:
        reserved = self.store.reserved_ports(target.workspace, exclude=target)
        http_base, gevent_base = self._bases(target)
        http = self._smallest_free(http_base, reserved)
        gevent = self._smallest_free(gevent_base, reserved | {http})
        ports = Ports(http=http, gevent=gevent)
        # write before the final bind check so concurrent starts see it
        self.store.write_ports(target, ports)
        if not (self.port_free(http) and self.port_free(gevent)):
            if previous is None:
                self.store.delete_ports(target)  # roll back new reservation
            else:
                self.store.write_ports(target, previous)  # keep pre-existing
            raise PortUnavailable(
                "allocated ports were taken before the server could start",
                hint="retry; if this persists another process is racing the port range",
            )
        return ports

    def _bases(self, target: Target) -> tuple[int, int]:
        conf = target.workspace.config
        return (
            self._base_from_conf(conf, "http_port", DEFAULT_HTTP_PORT),
            self._base_from_conf(conf, "gevent_port", DEFAULT_GEVENT_PORT),
        )

    @staticmethod
    def _base_from_conf(conf, key: str, default: int) -> int:
        value = conf.get(key) if conf else None
        return int(value) if value and value.isdigit() else default

    def _smallest_free(
        self, base: int, reserved: set[int], *, check_bind: bool = True
    ) -> int:
        port = base
        while port in reserved or (check_bind and not self.port_free(port)):
            port += 1
        return port

    def _diagnose(self, port: int) -> str:
        response = self.http_probe(port)
        if response and "odoo" in response.lower():
            return (
                "an Odoo server is (probably) already running for this "
                f"instance at http://localhost:{port}"
            )
        process = self._occupying_process(port)
        if process:
            return f"occupied by '{process}'"
        return "occupied by another process"

    def _occupying_process(self, port: int) -> str | None:
        result = self.runner.run(
            ["lsof", "-i", f":{port}", "-sTCP:LISTEN", "-Fc"], check=False
        )
        if result.returncode != 0:
            return None
        for line in result.stdout.splitlines():
            if line.startswith("c"):
                return line[1:]
        return None

    # -- lifecycle -----------------------------------------------------------

    def run_foreground(self, command) -> int:
        """Stream odoo-bin in the terminal; Ctrl-C stops it (v1 has no
        stop/restart). The ports file stays for the next start."""
        return self.runner.stream(
            command.argv, cwd=command.cwd, extra_env=command.env
        )
