import os
import tempfile
import unittest
from pathlib import Path

from odoo_cli.core import agent_assets
from odoo_cli.core.models import Workspace, Worktree
from tests.fixtures.workspace import make_env, make_workspace, make_worktree

MARKER = agent_assets.MARKER


def which_none(_cmd):
    return None


def which_only(*names):
    return lambda cmd: f"/usr/bin/{cmd}" if cmd in names else None


class AgentAssetsTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)
        self.env = make_env(self.home)
        # skills install into the workspace, not home
        self.root = make_workspace(self.home)
        self.claude_skills = self.root / ".claude" / "skills"
        self.agents_skills = self.root / ".agents" / "skills"


# --- workspace / worktree docs ----------------------------------------------


class TestWorkspaceDocs(AgentAssetsTestCase):
    def _workspace(self) -> Workspace:
        return Workspace(root=make_workspace(self.home), config=None)

    def write(self, ws, which=which_none):
        return agent_assets.write_workspace_docs(ws, env=self.env, which=which)

    def test_writes_agents_md_without_claude_symlink_by_default(self):
        ws = self._workspace()
        written = self.write(ws)  # no Claude detected

        agents = ws.root / "AGENTS.md"
        self.assertTrue(agents.is_file())
        self.assertIn(agents, written)
        self.assertFalse((ws.root / "CLAUDE.md").exists())

    def test_claude_symlink_only_when_claude_present(self):
        ws = self._workspace()
        written = self.write(ws, which=which_only("claude"))

        agents = ws.root / "AGENTS.md"
        claude = ws.root / "CLAUDE.md"
        self.assertTrue(claude.is_symlink())
        self.assertEqual(os.readlink(claude), "AGENTS.md")
        self.assertEqual(claude.read_text(), agents.read_text())
        self.assertIn(claude, written)

    def test_claude_desktop_app_triggers_symlink(self):
        (self.home / "Library" / "Application Support" / "Claude").mkdir(parents=True)
        ws = self._workspace()

        self.write(ws)  # no `claude` CLI, but the desktop app is present

        self.assertTrue((ws.root / "CLAUDE.md").is_symlink())

    def test_create_once_leaves_existing_untouched(self):
        ws = self._workspace()
        (ws.root / "AGENTS.md").write_text("my notes\n")

        written = self.write(ws)

        self.assertEqual((ws.root / "AGENTS.md").read_text(), "my notes\n")
        self.assertNotIn(ws.root / "AGENTS.md", written)

    def test_empty_agents_md_is_treated_as_absent(self):
        ws = self._workspace()
        (ws.root / "AGENTS.md").write_text("")

        written = self.write(ws)

        self.assertIn(ws.root / "AGENTS.md", written)
        self.assertIn("Odoo development workspace", (ws.root / "AGENTS.md").read_text())

    def test_idempotent(self):
        ws = self._workspace()
        self.write(ws, which=which_only("claude"))
        # a second run writes nothing and does not raise on the existing symlink
        self.assertEqual(self.write(ws, which=which_only("claude")), [])


class TestWorktreeDocs(AgentAssetsTestCase):
    def test_writes_thin_agents_md_without_claude_symlink(self):
        root = make_workspace(self.home)
        path = make_worktree(root, "19.0", version="19.0")
        worktree = Worktree(name="19.0", path=path)

        written = agent_assets.write_worktree_docs(worktree)

        self.assertEqual(written, [path / "AGENTS.md"])
        self.assertTrue((path / "AGENTS.md").is_file())
        self.assertFalse((path / "CLAUDE.md").exists())
        # idempotent
        self.assertEqual(agent_assets.write_worktree_docs(worktree), [])

    def test_empty_worktree_agents_md_is_treated_as_absent(self):
        root = make_workspace(self.home)
        path = make_worktree(root, "19.0", version="19.0")
        (path / "AGENTS.md").write_text("")
        worktree = Worktree(name="19.0", path=path)

        written = agent_assets.write_worktree_docs(worktree)

        self.assertEqual(written, [path / "AGENTS.md"])
        self.assertIn("Odoo worktree", (path / "AGENTS.md").read_text())


# --- harness detection ------------------------------------------------------


class TestSkillDirs(AgentAssetsTestCase):
    def dirs(self, which):
        return agent_assets._skill_dirs(self.root, self.env, which)

    def test_agents_dir_always_present(self):
        # no harness at all: the shared AGENTS.md dir is still written
        self.assertEqual(self.dirs(which_none), {self.agents_skills})

    def test_codex_or_opencode_is_still_just_agents(self):
        self.assertEqual(self.dirs(which_only("codex")), {self.agents_skills})
        self.assertEqual(self.dirs(which_only("opencode")), {self.agents_skills})

    def test_claude_cli_adds_claude_dir(self):
        self.assertEqual(
            self.dirs(which_only("claude")),
            {self.agents_skills, self.claude_skills},
        )

    def test_claude_config_dir_adds_claude_dir(self):
        (self.home / ".claude").mkdir(parents=True)
        self.assertEqual(
            self.dirs(which_none), {self.agents_skills, self.claude_skills}
        )

    def test_claude_desktop_macos_adds_claude_dir(self):
        (self.home / "Library" / "Application Support" / "Claude").mkdir(parents=True)
        self.assertEqual(
            self.dirs(which_none), {self.agents_skills, self.claude_skills}
        )

    def test_claude_desktop_linux_adds_claude_dir(self):
        (self.home / ".config" / "Claude").mkdir(parents=True)
        self.assertEqual(
            self.dirs(which_none), {self.agents_skills, self.claude_skills}
        )


# --- skill install / sync / uninstall ---------------------------------------


class TestSkills(AgentAssetsTestCase):
    def install(self, which=None):
        return agent_assets.install_skills(
            self.root, env=self.env, which=which or which_only("claude")
        )

    def test_installs_bundled_skills_with_marker(self):
        result = self.install()

        review = self.claude_skills / "odoo-review"
        self.assertTrue((review / "SKILL.md").is_file())
        self.assertTrue((review / MARKER).is_file())
        self.assertIn(review, result.installed)
        # the shared <workspace>/.agents/skills dir is always written too
        self.assertTrue((self.agents_skills / "odoo-review" / "SKILL.md").is_file())

    def test_agents_skills_installed_without_any_harness(self):
        result = self.install(which=which_none)
        self.assertTrue((self.agents_skills / "odoo-cli" / "SKILL.md").is_file())
        self.assertIn(self.agents_skills / "odoo-cli", result.installed)
        # no Claude detected: the Claude dir is left alone
        self.assertFalse(self.claude_skills.exists())

    def test_idempotent_resync(self):
        self.install()
        result = self.install()  # re-run overwrites in place, prunes nothing
        self.assertTrue((self.claude_skills / "odoo-cli" / MARKER).is_file())
        self.assertEqual(result.pruned, [])
        self.assertEqual(result.skipped, [])

    def test_resync_refreshes_marker_bearing_skill(self):
        self.install()
        skill = self.claude_skills / "odoo-cli" / "SKILL.md"
        skill.write_text("old bundled version\n")

        result = self.install()

        self.assertIn(self.claude_skills / "odoo-cli", result.installed)
        self.assertIn("Operating an Odoo workspace", skill.read_text())

    def test_prunes_marker_bearing_folder_no_longer_bundled(self):
        self.install()
        stale = self.claude_skills / "odoo-old"
        stale.mkdir()
        (stale / MARKER).write_text("")

        result = self.install()

        self.assertFalse(stale.exists())
        self.assertIn(stale, result.pruned)

    def test_skips_marker_less_collision(self):
        review = self.claude_skills / "odoo-review"
        review.mkdir(parents=True)
        (review / "SKILL.md").write_text("custom\n")  # user's own, no marker

        result = self.install()

        self.assertEqual((review / "SKILL.md").read_text(), "custom\n")
        self.assertFalse((review / MARKER).exists())
        self.assertIn(review, result.skipped)

    def test_uninstall_removes_only_marker_bearing(self):
        self.install()
        mine = self.claude_skills / "my-skill"
        mine.mkdir()
        (mine / "SKILL.md").write_text("mine\n")

        removed = agent_assets.uninstall_skills(
            self.root, env=self.env, which=which_only("claude")
        )

        self.assertTrue(mine.exists())
        self.assertFalse((self.claude_skills / "odoo-cli").exists())
        self.assertTrue(any(p.name == "odoo-cli" for p in removed))

    def test_prune_legacy_global_skills_removes_only_marker_bearing(self):
        # simulate an old global install under ~ plus a user's own global skill
        g_agents = self.home / ".agents" / "skills"
        g_claude = self.home / ".claude" / "skills"
        ours = g_agents / "odoo-cli"
        ours.mkdir(parents=True)
        (ours / MARKER).write_text("")
        ours_claude = g_claude / "odoo-review"
        ours_claude.mkdir(parents=True)
        (ours_claude / MARKER).write_text("")
        mine = g_agents / "my-own"
        mine.mkdir()
        (mine / "SKILL.md").write_text("mine\n")

        removed = agent_assets.prune_legacy_global_skills(env=self.env)

        self.assertFalse(ours.exists())
        self.assertFalse(ours_claude.exists())
        self.assertTrue(mine.exists())  # no marker → untouched
        self.assertEqual({p.name for p in removed}, {"odoo-cli", "odoo-review"})


# --- packaging: assets must ship and be readable as resources ---------------


class TestBundledAssets(AgentAssetsTestCase):
    def test_templates_and_skills_are_discoverable(self):
        assets = agent_assets._assets()
        self.assertIn("# Odoo", (assets / "AGENTS.md").read_text())
        self.assertIn("worktree", (assets / "AGENTS.worktree.md").read_text().lower())

        names = {name for name, _ in agent_assets._bundled_skills()}
        self.assertTrue({"odoo-cli", "odoo-review", "odoo-security"} <= names)

    def test_copy_tree_materializes_resources(self):
        # exercises the Traversable path (not a temp-dir Path) end to end
        dest = self.home / "out"
        src = agent_assets._assets() / "skills" / "odoo-cli"
        agent_assets._copy_tree(src, dest)
        self.assertTrue((dest / "SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
