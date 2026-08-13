import tempfile
import unittest
from pathlib import Path

from odoo_cli.core.errors import ReportDepsError
from odoo_cli.core.report_deps import MACOS_PKG_URL, ReportDepsService
from tests.fixtures.process import FakeProcessRunner


class ReportDepsTestCase(unittest.TestCase):
    def setUp(self):
        self.runner = FakeProcessRunner()
        self.tools: dict[str, str] = {}
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.downloads = Path(self._tmp.name)

    def service(self, platform="darwin", euid=501) -> ReportDepsService:
        return ReportDepsService(
            self.runner,
            which=self.tools.get,
            platform=platform,
            geteuid=lambda: euid,
            download_dir=self.downloads,
        )


class TestWkhtmltopdfPlan(ReportDepsTestCase):
    def test_darwin_downloads_official_pkg(self):
        # no brew: the project is gone from Homebrew, the .pkg is the only way
        self.tools["sudo"] = "/usr/bin/sudo"
        plan = self.service().wkhtmltopdf_plan()
        curl, installer = plan.commands
        self.assertEqual(curl[0], "curl")
        self.assertEqual(curl[-1], MACOS_PKG_URL)
        self.assertEqual(installer[:2], ("sudo", "installer"))
        self.assertEqual(installer[-2:], ("-target", "/"))
        # the pkg lands in the injected download dir, not /tmp
        self.assertTrue(installer[3].startswith(str(self.downloads)))

    def test_linux_uses_apt(self):
        self.tools["apt-get"] = "/usr/bin/apt-get"
        plan = self.service(platform="linux", euid=0).wkhtmltopdf_plan()
        self.assertEqual(plan.manager, "apt-get")
        self.assertEqual(
            plan.commands[-1],
            (
                "env", "DEBIAN_FRONTEND=noninteractive", "apt-get",
                "install", "-y", "wkhtmltopdf",
            ),
        )

    def test_linux_non_root_uses_sudo(self):
        self.tools["apt-get"] = "/usr/bin/apt-get"
        self.tools["sudo"] = "/usr/bin/sudo"
        plan = self.service(platform="linux").wkhtmltopdf_plan()
        self.assertEqual(plan.commands[0][0], "sudo")

    def test_linux_without_apt_is_actionable(self):
        with self.assertRaises(ReportDepsError) as cm:
            self.service(platform="linux", euid=0).wkhtmltopdf_plan()
        self.assertIn("package manager", cm.exception.hint)

    def test_unsupported_platform(self):
        with self.assertRaises(ReportDepsError):
            self.service(platform="win32").wkhtmltopdf_plan()


class TestWkhtmltopdfInstall(ReportDepsTestCase):
    def darwin_setup(self, probe_returncode=0):
        self.tools["sudo"] = "/usr/bin/sudo"

        def installed(call):
            self.tools["wkhtmltopdf"] = "/usr/local/bin/wkhtmltopdf"

        self.runner.expect_stream("curl")
        self.runner.expect_stream("sudo", "installer", effect=installed)
        self.runner.expect(
            "wkhtmltopdf", "--version",
            stdout="wkhtmltopdf 0.12.6\n", returncode=probe_returncode,
        )

    def test_darwin_install_streams_and_probes(self):
        self.darwin_setup()
        result = self.service().install_wkhtmltopdf()
        self.assertEqual(result.manager, "the official macOS package")
        self.assertEqual(result.warnings, ())
        self.assertEqual(self.runner.stream_calls[0][0], "curl")
        self.assertEqual(self.runner.stream_calls[1][:2], ("sudo", "installer"))

    def test_binary_that_does_not_run_warns_about_rosetta(self):
        # x86_64-only build: a fresh Apple Silicon machine lacks Rosetta 2
        self.darwin_setup(probe_returncode=134)
        result = self.service().install_wkhtmltopdf()
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("Rosetta", result.warnings[0])

    def test_failed_command_raises_with_the_command(self):
        self.tools["sudo"] = "/usr/bin/sudo"
        self.runner.expect_stream("curl", returncode=22)
        with self.assertRaises(ReportDepsError) as cm:
            self.service().install_wkhtmltopdf()
        self.assertIn("curl", cm.exception.hint)

    def test_missing_binary_after_install_raises(self):
        # streams succeed but the binary never appears on PATH
        self.tools["sudo"] = "/usr/bin/sudo"
        self.runner.expect_stream("curl")
        self.runner.expect_stream("sudo", "installer")
        with self.assertRaises(ReportDepsError) as cm:
            self.service().install_wkhtmltopdf()
        self.assertIn("PATH", cm.exception.hint)


class TestCairo(ReportDepsTestCase):
    def test_installed_needs_pkg_config_finding_cairo(self):
        self.assertFalse(self.service().cairo_installed())  # no pkg-config
        self.tools["pkg-config"] = "/usr/bin/pkg-config"
        self.runner.expect("pkg-config", "--exists", "cairo", returncode=1)
        self.assertFalse(self.service().cairo_installed())
        self.runner.expect("pkg-config", "--exists", "cairo", returncode=0)
        self.assertTrue(self.service().cairo_installed())

    def test_darwin_plan_uses_brew(self):
        self.tools["brew"] = "/opt/homebrew/bin/brew"
        plan = self.service().cairo_plan()
        self.assertEqual(plan.manager, "Homebrew")
        self.assertEqual(
            plan.commands, (("brew", "install", "cairo", "pkg-config"),)
        )

    def test_darwin_without_brew_is_actionable(self):
        with self.assertRaises(ReportDepsError) as cm:
            self.service().cairo_plan()
        self.assertIn("Homebrew", cm.exception.hint)

    def test_linux_plan_installs_dev_headers(self):
        self.tools["apt-get"] = "/usr/bin/apt-get"
        plan = self.service(platform="linux", euid=0).cairo_plan()
        self.assertEqual(
            plan.commands[-1],
            (
                "env", "DEBIAN_FRONTEND=noninteractive", "apt-get",
                "install", "-y", "libcairo2-dev", "pkg-config",
            ),
        )

    def test_install_verifies_pkg_config(self):
        self.tools["brew"] = "/opt/homebrew/bin/brew"

        def installed(call):
            self.tools["pkg-config"] = "/opt/homebrew/bin/pkg-config"

        self.runner.expect_stream("brew", "install", effect=installed)
        self.runner.expect("pkg-config", "--exists", "cairo", returncode=0)
        result = self.service().install_cairo()
        self.assertEqual(result.manager, "Homebrew")

    def test_install_that_leaves_cairo_missing_raises(self):
        self.tools["brew"] = "/opt/homebrew/bin/brew"
        self.runner.expect_stream("brew", "install")
        with self.assertRaises(ReportDepsError) as cm:
            self.service().install_cairo()
        self.assertIn("pkg-config", cm.exception.message)
