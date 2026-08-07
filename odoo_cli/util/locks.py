"""Advisory file locks serializing cross-process critical sections.

flock-based: the kernel releases the lock when the holder exits, so a
crashed process never wedges the workspace. Lock files are empty markers
that can be deleted at any time (deleting one only costs the exclusion of
holders that already have it open). POSIX-only, like the CLI itself.
"""

from __future__ import annotations

import fcntl
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def file_lock(path: Path) -> Iterator[None]:
    """Hold the exclusive lock on `path`, blocking until it is free."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
