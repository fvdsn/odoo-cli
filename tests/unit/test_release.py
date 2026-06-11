import tempfile
import unittest
from pathlib import Path

from odoo_cli.core.errors import InvalidWorkspace
from odoo_cli.core.release import normalize_version, read_release
from tests.fixtures.workspace import version_release_py


class TestReadRelease(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.worktree = Path(self._tmp.name)

    def write(self, content: str):
        release = self.worktree / "odoo" / "odoo" / "release.py"
        release.parent.mkdir(parents=True, exist_ok=True)
        release.write_text(content)

    def test_stable_version(self):
        self.write(version_release_py("19.0", py_min=(3, 10), py_max=(3, 13)))
        info = read_release(self.worktree)
        self.assertEqual(info.version, "19.0")
        self.assertEqual(info.py_min, (3, 10))
        self.assertEqual(info.py_max, (3, 13))

    def test_saas_version(self):
        self.write(version_release_py("saas-19.4"))
        info = read_release(self.worktree)
        self.assertEqual(info.version, "saas~19.4")
        self.assertEqual(normalize_version(info.version), "saas-19.4")

    def test_missing_py_range(self):
        self.write(version_release_py("17.0", py_min=None, py_max=None))
        info = read_release(self.worktree)
        self.assertEqual(info.version, "17.0")
        self.assertIsNone(info.py_min)
        self.assertIsNone(info.py_max)

    def test_missing_release_py(self):
        with self.assertRaises(InvalidWorkspace):
            read_release(self.worktree)
