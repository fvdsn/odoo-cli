import tempfile
import unittest
from pathlib import Path

from odoo_cli.core.errors import NoCompatiblePython
from odoo_cli.core.models import Workspace, Worktree
from odoo_cli.core.venvs import READY_MARKER, VenvService
from tests.fixtures.process import FakeProcessRunner
from tests.fixtures.workspace import make_workspace, make_worktree


class VenvTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)
        self.root = make_workspace(self.home)
        self.workspace = Workspace(root=self.root, config=None)
        self.runner = FakeProcessRunner()
        self.available: dict[str, str] = {}

    def service(self) -> VenvService:
        return VenvService(self.runner, which=self.available.get)

    def worktree(self, version="19.0", **kwargs) -> Worktree:
        path = make_worktree(self.root, "wt", version=version, **kwargs)
        (path / "odoo" / "requirements.txt").write_text("babel\n")
        return Worktree(name="wt", path=path)


class TestVenvPath(VenvTestCase):
    def test_normalized_version_dir(self):
        wt = self.worktree(version="saas-19.4")
        self.assertEqual(
            self.service().venv_path(self.workspace, wt),
            self.root / ".venvs" / "saas-19.4",
        )


class TestEnsure(VenvTestCase):
    def test_creates_with_uv_when_available(self):
        self.available = {"uv": "/usr/bin/uv", "python3.13": "/usr/bin/python3.13"}
        self.runner.expect("uv", stdout="")
        wt = self.worktree()
        result = self.service().ensure(self.workspace, wt)
        self.assertTrue(result.created)
        venv = self.root / ".venvs" / "19.0"
        self.assertEqual(
            self.runner.calls[0],
            ("uv", "venv", "--python", "/usr/bin/python3.13", str(venv)),
        )
        self.assertEqual(
            self.runner.calls[1],
            (
                "uv", "pip", "install", "--python", str(venv / "bin" / "python"),
                "-r", str(wt.path / "odoo" / "requirements.txt"),
            ),
        )
        self.assertTrue((venv / READY_MARKER).is_file())

    def test_uv_provisions_missing_interpreter(self):
        self.available = {"uv": "/usr/bin/uv"}
        self.runner.expect("uv", stdout="")
        result = self.service().ensure(self.workspace, self.worktree())
        self.assertTrue(result.created)
        self.assertEqual(self.runner.calls[0][:3], ("uv", "venv", "--python"))
        self.assertEqual(self.runner.calls[0][3], ">=3.10,<3.14")

    def test_fallback_python_venv_picks_highest_compatible(self):
        self.available = {
            "python3.12": "/usr/bin/python3.12",
            "python3.13": "/usr/bin/python3.13",
        }
        self.runner.expect("/usr/bin/python3.13", stdout="")
        venv = self.root / ".venvs" / "19.0"
        self.runner.expect(str(venv / "bin" / "python"), stdout="")
        self.service().ensure(self.workspace, self.worktree())
        self.assertEqual(
            self.runner.calls[0],
            ("/usr/bin/python3.13", "-m", "venv", str(venv)),
        )
        self.assertEqual(
            self.runner.calls[1][:4],
            (str(venv / "bin" / "python"), "-m", "pip", "install"),
        )

    def test_no_interpreter_no_uv_is_actionable(self):
        with self.assertRaises(NoCompatiblePython) as cm:
            self.service().ensure(self.workspace, self.worktree())
        self.assertIn("python3.13", cm.exception.hint)
        self.assertIn("uv", cm.exception.hint)

    def test_ready_venv_is_reused(self):
        wt = self.worktree()
        venv = self.root / ".venvs" / "19.0"
        (venv / "bin").mkdir(parents=True)
        (venv / "bin" / "python").write_text("")
        (venv / READY_MARKER).touch()
        result = self.service().ensure(self.workspace, wt)
        self.assertFalse(result.created)
        self.assertEqual(self.runner.calls, [])

    def test_incomplete_venv_is_recreated(self):
        self.available = {"uv": "/usr/bin/uv"}
        self.runner.expect("uv", stdout="")
        wt = self.worktree()
        venv = self.root / ".venvs" / "19.0"
        (venv / "bin").mkdir(parents=True)
        (venv / "bin" / "python").write_text("")  # no ready marker
        result = self.service().ensure(self.workspace, wt)
        self.assertTrue(result.created)
        self.assertTrue(self.runner.calls)
