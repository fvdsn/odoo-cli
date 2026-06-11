"""Socket helpers for port allocation and diagnostics."""

from __future__ import annotations

import socket


def port_free(port: int) -> bool:
    """Availability is verified by binding, never by trusting a file."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("", port))
            return True
        except OSError:
            return False


def http_probe(port: int, host: str = "127.0.0.1", timeout: float = 1.0) -> str | None:
    """Best-effort HTTP exchange with whatever listens on the port.

    Returns the start of the response text, or None when nothing answers
    HTTP-ish. Used to tell 'an Odoo server is already running' apart from 'a
    foreign process holds the port'."""
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(b"GET / HTTP/1.0\r\nHost: localhost\r\n\r\n")
            return sock.recv(2048).decode("utf-8", errors="replace")
    except OSError:
        return None
