import errno
import fcntl
import os
import tempfile
import unittest
from pathlib import Path

from odoo_cli.util.locks import file_lock


class TestFileLock(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "deep" / "nested" / "test.lock"

    def _try_flock(self) -> bool:
        """Whether an independent file description can take the lock now.
        flock is per open-file-description, so this conflicts even within
        one process."""
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.assertIn(exc.errno, (errno.EACCES, errno.EAGAIN))
            return False
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)
            return True
        finally:
            os.close(fd)

    def test_creates_parents_and_excludes_while_held(self):
        with file_lock(self.path):
            self.assertTrue(self.path.is_file())
            self.assertFalse(self._try_flock())
        self.assertTrue(self._try_flock())

    def test_released_on_exception(self):
        with self.assertRaises(RuntimeError):
            with file_lock(self.path):
                raise RuntimeError("boom")
        self.assertTrue(self._try_flock())
