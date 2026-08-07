import tempfile
import unittest
from pathlib import Path

from odoo_cli.core import filestore
from odoo_cli.core.odoo_conf import OdooConf


def conf_with(tmp: Path, body: str = "") -> OdooConf:
    path = tmp / "odoo.conf"
    path.write_text(f"[options]\n{body}")
    return OdooConf.load(path)


class TestDataDir(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.home = Path("/home/dev")

    def test_conf_data_dir_wins(self):
        conf = conf_with(self.tmp, "data_dir = /srv/odoo-data\n")
        result = filestore.data_dir(
            conf, environ={}, platform="linux", home=self.home
        )
        self.assertEqual(result, Path("/srv/odoo-data"))

    def test_darwin_default(self):
        conf = conf_with(self.tmp)
        result = filestore.data_dir(
            conf, environ={}, platform="darwin", home=self.home
        )
        self.assertEqual(
            result, self.home / "Library" / "Application Support" / "Odoo"
        )

    def test_xdg_data_home(self):
        conf = conf_with(self.tmp)
        result = filestore.data_dir(
            conf, environ={"XDG_DATA_HOME": "/xdg"}, platform="linux", home=self.home
        )
        self.assertEqual(result, Path("/xdg/Odoo"))

    def test_linux_default(self):
        conf = conf_with(self.tmp)
        result = filestore.data_dir(
            conf, environ={}, platform="linux", home=self.home
        )
        self.assertEqual(result, self.home / ".local" / "share" / "Odoo")

    def test_false_is_unset(self):
        conf = conf_with(self.tmp, "data_dir = False\n")
        result = filestore.data_dir(
            conf, environ={}, platform="linux", home=self.home
        )
        self.assertEqual(result, self.home / ".local" / "share" / "Odoo")

    def test_filestore_path(self):
        conf = conf_with(self.tmp, "data_dir = /srv/odoo-data\n")
        result = filestore.filestore_path(
            conf, "alpha", environ={}, platform="linux", home=self.home
        )
        self.assertEqual(result, Path("/srv/odoo-data/filestore/alpha"))
