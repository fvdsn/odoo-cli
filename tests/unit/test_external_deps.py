import tempfile
import unittest
from pathlib import Path

from odoo_cli.core import external_deps
from odoo_cli.core.errors import ExternalDependencyNotInstallable
from odoo_cli.core.models import Worktree
from odoo_cli.util.process import ProcessError, ProcessResult
from tests.fixtures.process import FakeProcessRunner
from tests.fixtures.workspace import make_workspace, make_worktree


def write_manifest(worktree: Path, module: str, body: str) -> None:
    mod = worktree / "odoo" / "addons" / module
    mod.mkdir(parents=True)
    (mod / "__manifest__.py").write_text(body)


class ExternalDepsTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        home = Path(self._tmp.name).resolve()
        self.root = make_workspace(home)
        path = make_worktree(self.root, "19.0", version="19.0")
        self.worktree = Worktree(name="19.0", path=path)

    def test_python_deps_collected_per_distribution(self):
        write_manifest(
            self.worktree.path, "mod_a",
            "{'name': 'A', 'external_dependencies': {'python': ['phonenumbers']}}",
        )
        write_manifest(
            self.worktree.path, "mod_b",
            "{'name': 'B', 'external_dependencies': {'python': ['phonenumbers>=8', 'pdf417gen']}}",
        )
        write_manifest(self.worktree.path, "mod_c", "{'name': 'C'}")
        deps = external_deps.python_deps(
            self.worktree, ["mod_a", "mod_b", "mod_c", "absent"]
        )
        self.assertEqual(
            deps, {"phonenumbers": ["mod_a", "mod_b"], "pdf417gen": ["mod_b"]}
        )

    def test_broken_manifest_is_ignored(self):
        write_manifest(self.worktree.path, "mod_bad", "{'name': 'oops'")
        self.assertEqual(external_deps.python_deps(self.worktree, ["mod_bad"]), {})

    def test_missing_distributions_probes_the_venv_python(self):
        runner = FakeProcessRunner()
        runner.expect("/venv/bin/python", "-c", stdout="pdf417gen\n")
        missing = external_deps.missing_distributions(
            runner, Path("/venv/bin/python"), ["phonenumbers", "pdf417gen"]
        )
        self.assertEqual(missing, ["pdf417gen"])
        argv = runner.calls[0]
        self.assertEqual(argv[0], "/venv/bin/python")
        self.assertEqual(argv[-2:], ("pdf417gen", "phonenumbers"))  # sorted

    def test_no_names_no_probe(self):
        runner = FakeProcessRunner()
        self.assertEqual(
            external_deps.missing_distributions(runner, Path("/p"), []), []
        )
        self.assertEqual(runner.calls, [])

    def test_none_scans_every_module(self):
        write_manifest(
            self.worktree.path, "mod_a",
            "{'name': 'A', 'external_dependencies': {'python': ['phonenumbers']}}",
        )
        deps = external_deps.python_deps(self.worktree, None)
        self.assertEqual(deps, {"phonenumbers": ["mod_a"]})


class FakeVenvs:
    def __init__(self, fail=False):
        self.fail = fail
        self.installed = []

    def install_packages(self, venv, packages):
        if self.fail:
            raise ProcessError(
                ProcessResult(argv=("pip",), returncode=1, stdout="", stderr="no wheel")
            )
        self.installed.append((venv, tuple(packages)))


class EnsureModuleDepsTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        home = Path(self._tmp.name).resolve()
        self.root = make_workspace(home)
        path = make_worktree(self.root, "19.0", version="19.0")
        self.worktree = Worktree(name="19.0", path=path)
        write_manifest(
            self.worktree.path, "mod_a",
            "{'name': 'A', 'external_dependencies': {'python': ['phonenumbers']}}",
        )
        self.runner = FakeProcessRunner()
        self.runner.expect("/v/bin/python", "-c", stdout="phonenumbers\n")

    def _ensure(self, venvs):
        return external_deps.ensure_module_deps(
            venvs, self.runner, self.worktree, ["mod_a"],
            Path("/v"), Path("/v/bin/python"),
        )

    def test_installs_missing(self):
        venvs = FakeVenvs()
        self._ensure(venvs)
        self.assertEqual(venvs.installed, [(Path("/v"), ("phonenumbers",))])

    def test_nothing_missing_installs_nothing(self):
        self.runner.expect("/v/bin/python", "-c", stdout="")
        venvs = FakeVenvs()
        self._ensure(venvs)
        self.assertEqual(venvs.installed, [])

    def test_install_failure_raises_typed_error(self):
        with self.assertRaises(ExternalDependencyNotInstallable) as caught:
            self._ensure(FakeVenvs(fail=True))
        self.assertIn("phonenumbers (needed by mod_a)", caught.exception.message)
        self.assertIn("pip install phonenumbers", caught.exception.hint)


class VenvManifestDepsTestCase(ExternalDepsTestCase):
    def test_rebuild_installs_manifest_deps(self):
        from odoo_cli.core.models import Workspace
        from odoo_cli.core.venvs import VenvService

        write_manifest(
            self.worktree.path, "mod_a",
            "{'name': 'A', 'external_dependencies': {'python': ['phonenumbers']}}",
        )
        runner = FakeProcessRunner()
        which = lambda name: None if name == "uv" else f"/usr/bin/{name}"  # noqa: E731
        service = VenvService(runner, which)
        workspace = Workspace(root=self.root, config=None)
        venv = service.venv_path(workspace, self.worktree)
        python = str(service.python_path(venv))
        runner.expect("/usr/bin/python3.13", stdout="")  # venv creation
        runner.expect("pkg-config", returncode=1)  # no cairo: no rlPyCairo
        runner.expect(python, "-c", stdout="phonenumbers\n")  # probe: missing
        runner.expect(python, "-m", "pip", "install", stdout="")
        result = service.rebuild(workspace, self.worktree)
        self.assertTrue(result.created)
        self.assertIn(
            (python, "-m", "pip", "install", "phonenumbers"), runner.calls
        )
