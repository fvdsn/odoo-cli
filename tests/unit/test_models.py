import os
import tempfile
import unittest
from pathlib import Path

from odoo_cli.core.models import Target, Worktree


class TestWorktree(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_full_worktree(self):
        (self.root / "19.0" / "odoo").mkdir(parents=True)
        wt = Worktree(name="19.0", path=self.root / "19.0")
        self.assertFalse(wt.is_linked)
        self.assertIsNone(wt.linked_from)

    def test_linked_worktree(self):
        (self.root / "19.0" / "odoo").mkdir(parents=True)
        (self.root / "customer-a").mkdir()
        os.symlink("../19.0/odoo", self.root / "customer-a" / "odoo")
        wt = Worktree(name="customer-a", path=self.root / "customer-a")
        self.assertTrue(wt.is_linked)
        self.assertEqual(wt.linked_from, "19.0")


class TestTarget(unittest.TestCase):
    def test_test_database_convention(self):
        target = Target(workspace=None, worktree=None, database="customer-a")
        self.assertEqual(target.test_database, "customer-a-test")
