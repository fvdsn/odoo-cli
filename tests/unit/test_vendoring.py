import unittest


class TestVendoredClick(unittest.TestCase):
    def test_click_compat_module(self):
        from odoo_cli.cli._click import click

        self.assertTrue(hasattr(click, "command"))
        self.assertTrue(hasattr(click, "testing"))

    def test_core_does_not_import_click(self):
        # Guard the layering rule: nothing under odoo_cli/core may import
        # click, vendored or not.
        import pathlib

        core = pathlib.Path(__file__).resolve().parents[2] / "odoo_cli" / "core"
        if not core.exists():
            self.skipTest("core package not created yet")
        for path in core.rglob("*.py"):
            source = path.read_text()
            self.assertNotIn("import click", source, f"{path} imports click")
            self.assertNotIn("_vendor", source, f"{path} imports vendored code")
