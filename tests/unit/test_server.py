import tempfile
import unittest
from pathlib import Path

from odoo_cli.core.errors import PortUnavailable
from odoo_cli.core.models import Ports, Target, Workspace, Worktree
from odoo_cli.core.odoo_conf import OdooConf
from odoo_cli.core.server import RunStateStore, ServerService
from tests.fixtures.process import FakeProcessRunner
from tests.fixtures.workspace import make_workspace, make_worktree


class ServerTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)
        self.root = make_workspace(self.home)
        self.conf = OdooConf.load(self.home / "odoo.conf")
        self.workspace = Workspace(root=self.root, config=self.conf)
        self.store = RunStateStore()
        self.runner = FakeProcessRunner()
        self.busy: set[int] = set()
        self.probe_response: str | None = None

    def service(self, port_free=None) -> ServerService:
        return ServerService(
            self.store,
            self.runner,
            port_free=port_free or (lambda p: p not in self.busy),
            http_probe=lambda p: self.probe_response,
        )

    def target(self, worktree="19.0", db=None) -> Target:
        if not (self.root / worktree).exists():
            make_worktree(self.root, worktree, version="19.0")
        return Target(
            workspace=self.workspace,
            worktree=Worktree(name=worktree, path=self.root / worktree),
            database=db or worktree,
        )


class TestRunStateStore(ServerTestCase):
    def test_roundtrip(self):
        target = self.target()
        self.assertIsNone(self.store.read_ports(target))
        self.store.write_ports(target, Ports(http=8069, gevent=8072))
        self.assertEqual(
            (self.root / ".run" / "19.0" / "19.0" / "ports").read_text(),
            "http=8069\ngevent=8072\n",
        )
        self.assertEqual(self.store.read_ports(target), Ports(8069, 8072))

    def test_stale_worktree_reservations_ignored(self):
        gone = self.target(worktree="gone")
        self.store.write_ports(gone, Ports(8069, 8072))
        import shutil

        shutil.rmtree(self.root / "gone")
        self.assertEqual(self.store.reserved_ports(self.workspace), set())

    def test_reserved_ports_excludes_target(self):
        a, b = self.target("19.0"), self.target("master")
        self.store.write_ports(a, Ports(8069, 8072))
        self.store.write_ports(b, Ports(8070, 8073))
        self.assertEqual(
            self.store.reserved_ports(self.workspace, exclude=a), {8070, 8073}
        )


class TestAllocation(ServerTestCase):
    def test_first_allocation_uses_defaults(self):
        ports = self.service().allocate_ports(self.target())
        self.assertEqual(ports, Ports(8069, 8072))
        self.assertEqual(self.store.read_ports(self.target()), ports)

    def test_second_instance_skips_reservations(self):
        first = self.target("19.0")
        self.service().allocate_ports(first)
        second = self.target("master")
        ports = self.service().allocate_ports(second)
        self.assertEqual(ports, Ports(8070, 8073))

    def test_shared_pool_http_never_walks_onto_gevent(self):
        self.service().allocate_ports(self.target("19.0"))  # 8069/8072
        self.busy.update({8070, 8071})
        ports = self.service().allocate_ports(self.target("master"))
        # 8069 reserved, 8070-8071 busy, 8072 reserved (gevent) -> 8073
        self.assertEqual(ports.http, 8073)
        self.assertEqual(ports.gevent, 8074)

    def test_existing_reservation_is_reused(self):
        target = self.target()
        self.store.write_ports(target, Ports(9999, 9998))
        ports = self.service().allocate_ports(target)
        self.assertEqual(ports, Ports(9999, 9998))

    def test_busy_reserved_port_refuses_with_odoo_diagnostic(self):
        target = self.target()
        self.store.write_ports(target, Ports(8069, 8072))
        self.busy.add(8069)
        self.probe_response = "HTTP/1.0 303 SEE OTHER\r\nSet-Cookie: session_id=..odoo.."
        with self.assertRaises(PortUnavailable) as cm:
            self.service().allocate_ports(target)
        self.assertIn("already running", cm.exception.message)
        self.assertIn("--new-port", cm.exception.hint)

    def test_busy_reserved_port_names_foreign_process(self):
        target = self.target()
        self.store.write_ports(target, Ports(8069, 8072))
        self.busy.add(8069)
        self.runner.expect("lsof", stdout="p123\ncnode\n")
        with self.assertRaises(PortUnavailable) as cm:
            self.service().allocate_ports(target)
        self.assertIn("node", cm.exception.message)

    def test_new_port_reallocates(self):
        target = self.target()
        self.store.write_ports(target, Ports(8069, 8072))
        self.busy.add(8069)
        ports = self.service().allocate_ports(target, new_port=True)
        # own reservation no longer counts: http moves off busy 8069,
        # gevent reclaims the still-free 8072
        self.assertEqual(ports, Ports(8070, 8072))
        self.assertEqual(self.store.read_ports(target), ports)

    def test_conf_base_ports(self):
        self.conf.set("http_port", "9000")
        self.conf.set("gevent_port", "9100")
        ports = self.service().allocate_ports(self.target())
        self.assertEqual(ports, Ports(9000, 9100))

    def test_failed_final_bind_rolls_back_new_reservation(self):
        # free during the scan, busy at the final check
        answers = iter([True, True, False])
        service = self.service(port_free=lambda p: next(answers, False))
        target = self.target()
        with self.assertRaises(PortUnavailable):
            service.allocate_ports(target)
        self.assertIsNone(self.store.read_ports(target))

    def test_failed_final_bind_keeps_preexisting_reservation(self):
        target = self.target()
        self.store.write_ports(target, Ports(8069, 8072))
        self.busy.add(8069)
        answers = iter([True, True, False])
        service = self.service(port_free=lambda p: next(answers, False))
        with self.assertRaises(PortUnavailable):
            service.allocate_ports(target, new_port=True)
        self.assertEqual(self.store.read_ports(target), Ports(8069, 8072))
