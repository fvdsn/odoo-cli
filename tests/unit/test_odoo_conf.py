import tempfile
import unittest
from pathlib import Path

from odoo_cli.core.odoo_conf import (
    DEFAULTS,
    REDACTED,
    OdooConf,
    demo_enabled,
    write_defaults,
)


class TestOdooConf(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "config" / "odoo" / "odoo.conf"

    def test_load_missing_file_is_empty(self):
        conf = OdooConf.load(self.path)
        self.assertFalse(conf.exists)
        self.assertIsNone(conf.get("db_host"))
        self.assertEqual(conf.missing_defaults(), list(DEFAULTS))

    def test_write_defaults_roundtrip(self):
        write_defaults(self.path)
        conf = OdooConf.load(self.path)
        self.assertEqual(conf.get("dev_mode"), "all")
        self.assertEqual(conf.get("log_level"), "warn")
        self.assertEqual(conf.missing_defaults(), [])
        # unset postgres keys are omitted, not written as the literal
        # "False": odoo-bin warns about those on every run
        self.assertIsNone(conf.get("db_host"))
        self.assertIsNone(conf.get("db_password"))

    def test_set_preserves_unknown_keys(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(
            "[options]\nproxy_mode = True\ndb_user = odoo\n"
        )
        conf = OdooConf.load(self.path)
        conf.set("db_user", "dev")
        conf.save()
        reloaded = OdooConf.load(self.path)
        self.assertEqual(reloaded.get("proxy_mode"), "True")
        self.assertEqual(reloaded.get("db_user"), "dev")

    def test_malformed_file_raises_typed_error(self):
        # a hand-edit gone wrong must not brick every command (including
        # `odoo config set`, the repair tool) with a parser traceback
        from odoo_cli.core.errors import OdooCliError

        self.path.parent.mkdir(parents=True)
        self.path.write_text("db_user = me\n")  # no [options] header
        with self.assertRaises(OdooCliError) as cm:
            OdooConf.load(self.path)
        self.assertIn(str(self.path), cm.exception.message)
        self.assertIn("odoo init", cm.exception.hint)

    def test_percent_in_values_is_literal(self):
        # odoo-bin parses odoo.conf with RawConfigParser: '%' has no special
        # meaning, and a password containing one must round-trip untouched
        write_defaults(self.path)
        conf = OdooConf.load(self.path)
        conf.set("db_password", "p%ss%%word")
        conf.save()
        reloaded = OdooConf.load(self.path)
        self.assertEqual(reloaded.get("db_password"), "p%ss%%word")
        self.assertEqual(reloaded.items(reveal=True)["db_password"], "p%ss%%word")

    def test_items_redacts_secrets(self):
        write_defaults(self.path)
        conf = OdooConf.load(self.path)
        conf.set("db_password", "hunter2")
        self.assertEqual(conf.items()["db_password"], REDACTED)
        self.assertEqual(conf.items(reveal=True)["db_password"], "hunter2")
        # get() is the explicit reveal path
        self.assertEqual(conf.get("db_password"), "hunter2")


class TestDemoEnabled(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.conf = OdooConf.load(Path(self._tmp.name) / "odoo.conf")

    def test_explicit_falsy_without_demo_enables_demo(self):
        # mirrors odoo's _check_bool falsy spellings, inverted
        for value in ("False", "false", "0", "no", "off", " False "):
            self.conf.set("without_demo", value)
            self.assertTrue(demo_enabled(self.conf), value)

    def test_absent_or_truthy_disables_demo(self):
        # odoo >= 19 defaults to no demo when the key is absent
        self.assertFalse(demo_enabled(self.conf))
        self.assertFalse(demo_enabled(None))
        for value in ("True", "1", "yes", "on"):
            self.conf.set("without_demo", value)
            self.assertFalse(demo_enabled(self.conf), value)
