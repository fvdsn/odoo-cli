import tempfile
import unittest
from pathlib import Path

from odoo_cli.core.addons import resolve_addons_paths
from odoo_cli.core.models import Worktree
from tests.fixtures.workspace import make_workspace, make_worktree


class AddonsTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)
        self.root = make_workspace(self.home)

    def worktree(self, name="19.0", **kwargs) -> Worktree:
        path = make_worktree(self.root, name, version="19.0", **kwargs)
        return Worktree(name=name, path=path)

    def add_module(self, *parts: str):
        module = self.root.joinpath(*parts)
        module.mkdir(parents=True, exist_ok=True)
        (module / "__manifest__.py").write_text("{}\n")


class TestResolveAddonsPaths(AddonsTestCase):
    def test_base_only(self):
        wt = self.worktree()
        self.assertEqual(resolve_addons_paths(wt), [wt.path / "odoo" / "addons"])

    def test_standard_repo_order(self):
        wt = self.worktree(repos=("documentation", "enterprise", "themes"))
        self.assertEqual(
            resolve_addons_paths(wt),
            [
                wt.path / "odoo" / "addons",
                wt.path / "themes",
                wt.path / "enterprise",
            ],
        )

    def test_custom_multi_addon_repos_alphabetical(self):
        wt = self.worktree()
        self.add_module("19.0", "support-tools", "tool_b")
        self.add_module("19.0", "customer-a-addons", "addon_a")
        self.assertEqual(
            resolve_addons_paths(wt),
            [
                wt.path / "odoo" / "addons",
                wt.path / "customer-a-addons",
                wt.path / "support-tools",
            ],
        )

    def test_single_addon_directory_adds_worktree_root(self):
        wt = self.worktree()
        self.add_module("19.0", "my_single_addon")
        self.assertEqual(
            resolve_addons_paths(wt),
            [wt.path / "odoo" / "addons", wt.path],
        )

    def test_root_added_once_and_sorted_first(self):
        wt = self.worktree()
        self.add_module("19.0", "addon_one")
        self.add_module("19.0", "addon_two")
        self.add_module("19.0", "zz-repo", "mod")
        self.assertEqual(
            resolve_addons_paths(wt),
            [wt.path / "odoo" / "addons", wt.path, wt.path / "zz-repo"],
        )

    def test_ignores_hidden_non_addon_and_known_repos(self):
        wt = self.worktree(repos=("documentation",))
        self.add_module("19.0", "upgrade", "fake_module")
        self.add_module("19.0", ".hidden", "fake_module")
        (wt.path / "dumps").mkdir()
        (wt.path / "notes.txt").write_text("")
        self.assertEqual(resolve_addons_paths(wt), [wt.path / "odoo" / "addons"])

    def test_linked_worktree_with_symlinked_standard_repos(self):
        source = self.worktree(name="19.0", repos=("documentation", "enterprise"))
        linked_path = make_worktree(
            self.root, "customer-a", linked_from="19.0",
            repos=("documentation", "enterprise"),
        )
        self.add_module("customer-a", "customer-a-addons", "addon_a")
        wt = Worktree(name="customer-a", path=linked_path)
        self.assertEqual(
            resolve_addons_paths(wt),
            [
                wt.path / "odoo" / "addons",
                wt.path / "enterprise",
                wt.path / "customer-a-addons",
            ],
        )
        self.assertTrue(source.path.exists())
