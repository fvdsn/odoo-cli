import tempfile
import unittest
from pathlib import Path

from odoo_cli.core.errors import PostgresError
from odoo_cli.core.odoo_conf import OdooConf
from odoo_cli.core.postgres import PostgresService
from tests.fixtures.process import FakeProcessRunner


class PostgresTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.conf = OdooConf.load(Path(self._tmp.name) / "odoo.conf")
        self.runner = FakeProcessRunner()
        self.service = PostgresService(self.runner, which=lambda n: None)


class TestEnv(PostgresTestCase):
    def test_false_values_are_not_exported(self):
        self.conf.set("db_host", "False")
        self.conf.set("db_user", "dev")
        self.conf.set("db_password", "hunter2")
        env = self.service.env(self.conf)
        self.assertEqual(env, {"PGUSER": "dev", "PGPASSWORD": "hunter2"})

    def test_password_via_env_not_argv(self):
        self.conf.set("db_password", "hunter2")
        self.runner.expect("psql", stdout="1\n")
        self.service.check_connection(self.conf)
        for call in self.runner.calls:
            self.assertNotIn("hunter2", " ".join(call))


class TestDatabases(PostgresTestCase):
    def test_db_exists(self):
        self.runner.expect("psql", stdout="1\n")
        self.assertTrue(self.service.db_exists(self.conf, "x"))
        self.runner.expect("psql", stdout="\n")
        self.assertFalse(self.service.db_exists(self.conf, "x"))

    def test_create_db_failure_is_typed(self):
        self.runner.expect("createdb", returncode=1, stderr="permission denied")
        with self.assertRaises(PostgresError) as cm:
            self.service.create_db(self.conf, "x")
        self.assertIn("permission denied", cm.exception.hint)

    def test_drop_terminates_connections_first(self):
        self.runner.expect("psql", stdout="")
        self.runner.expect("dropdb", stdout="")
        self.service.drop_db(self.conf, "x")
        self.assertIn("pg_terminate_backend", self.runner.calls[0][3])
        self.assertEqual(self.runner.calls[1][0], "dropdb")

    def test_sql_returns_rows(self):
        self.runner.expect("psql", stdout="crm\nsale\n\n")
        rows = self.service.sql(self.conf, "db", "SELECT name FROM x")
        self.assertEqual(rows, ["crm", "sale"])

    def test_db_name_literals_are_quoted(self):
        from odoo_cli.core.postgres import quote_literal

        self.assertEqual(quote_literal("customer-a"), "'customer-a'")
        self.assertEqual(quote_literal("bad'name"), "'bad''name'")
        self.runner.expect("psql", stdout="")
        self.service.db_exists(self.conf, "bad'name")
        query = self.runner.calls[0][3]
        self.assertIn("'bad''name'", query)


class TestDetectLocalPorts(PostgresTestCase):
    def make_service(self, tools=None):
        self.sockets = Path(self._tmp.name) / "sockets"
        self.sockets.mkdir(exist_ok=True)
        return PostgresService(
            self.runner,
            which=(tools or {}).get,
            socket_dirs=(self.sockets,),
        )

    def test_ports_from_socket_files(self):
        service = self.make_service()
        (self.sockets / ".s.PGSQL.5433").touch()
        (self.sockets / ".s.PGSQL.5433.lock").touch()  # suffix not a port
        self.runner.expect("psql", "--no-psqlrc", "-p", "5433", stdout="1\n")
        self.assertEqual(service.detect_local_ports(self.conf), [5433])

    def test_silent_ports_are_filtered(self):
        service = self.make_service()
        (self.sockets / ".s.PGSQL.5433").touch()
        (self.sockets / ".s.PGSQL.5434").touch()
        self.runner.expect("psql", returncode=2)
        self.runner.expect("psql", "--no-psqlrc", "-p", "5434", stdout="1\n")
        self.assertEqual(service.detect_local_ports(self.conf), [5434])

    def test_ports_from_pg_lsclusters(self):
        service = self.make_service(tools={"pg_lsclusters": "/usr/bin/pg_lsclusters"})
        self.runner.expect(
            "pg_lsclusters",
            stdout=(
                "17 main 5434 online postgres /var/lib/postgresql/17/main log\n"
                "16 old 5435 down postgres /var/lib/postgresql/16/old log\n"
            ),
        )
        self.runner.expect("psql", "--no-psqlrc", "-p", "5434", stdout="1\n")
        # the down cluster is never probed: an unexpected psql would fail here
        self.assertEqual(service.detect_local_ports(self.conf), [5434])

    def test_missing_socket_dir_yields_nothing(self):
        service = PostgresService(
            self.runner,
            which=lambda n: None,
            socket_dirs=(Path(self._tmp.name) / "nope",),
        )
        self.assertEqual(service.detect_local_ports(self.conf), [])


class TestInstall(PostgresTestCase):
    def make_service(self, tools, *, platform="linux", euid=0):
        return PostgresService(
            self.runner,
            which=tools.get,
            platform=platform,
            geteuid=lambda: euid,
            current_user=lambda: "dev",
        )

    def test_linux_apt_install_as_root(self):
        tools = {"apt-get": "/usr/bin/apt-get", "psql": None}

        def install_effect(call):
            tools["psql"] = "/usr/bin/psql"

        self.runner.expect_stream(
            "env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "update"
        )
        self.runner.expect_stream(
            "env",
            "DEBIAN_FRONTEND=noninteractive",
            "apt-get",
            "install",
            "-y",
            "postgresql",
            effect=install_effect,
        )
        result = self.make_service(tools).install()

        self.assertEqual(result.manager, "apt-get")
        self.assertEqual(
            self.runner.stream_calls,
            [
                ("env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "update"),
                (
                    "env",
                    "DEBIAN_FRONTEND=noninteractive",
                    "apt-get",
                    "install",
                    "-y",
                    "postgresql",
                ),
            ],
        )
        self.assertIn("service manager", result.warnings[0])

    def test_linux_apt_uses_sudo_when_not_root(self):
        tools = {
            "apt-get": "/usr/bin/apt-get",
            "sudo": "/usr/bin/sudo",
            "service": "/usr/sbin/service",
            "psql": None,
        }

        def install_effect(call):
            tools["psql"] = "/usr/bin/psql"

        self.runner.expect_stream(
            "sudo", "env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "update"
        )
        self.runner.expect_stream(
            "sudo",
            "env",
            "DEBIAN_FRONTEND=noninteractive",
            "apt-get",
            "install",
            "-y",
            "postgresql",
            effect=install_effect,
        )
        self.runner.expect_stream("sudo", "service", "postgresql", "start")
        self.runner.expect("sudo", "-u", "postgres", "createuser")

        result = self.make_service(tools, euid=1000).install()

        self.assertEqual(result.warnings, ())
        self.assertEqual(
            self.runner.stream_calls[0],
            ("sudo", "env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "update"),
        )

    def test_macos_homebrew_install(self):
        tools = {"brew": "/opt/homebrew/bin/brew", "psql": None}

        def install_effect(call):
            tools["psql"] = "/opt/homebrew/bin/psql"

        self.runner.expect_stream("brew", "install", "postgresql", effect=install_effect)
        self.runner.expect_stream("brew", "services", "start", "postgresql")

        result = self.make_service(tools, platform="darwin").install()

        self.assertEqual(result.manager, "Homebrew")
        self.assertEqual(result.warnings, ())
        self.assertEqual(
            self.runner.stream_calls,
            [
                ("brew", "install", "postgresql"),
                ("brew", "services", "start", "postgresql"),
            ],
        )

    def test_start_falls_back_from_systemctl_to_service(self):
        tools = {
            "apt-get": "/usr/bin/apt-get",
            "runuser": "/usr/sbin/runuser",
            "systemctl": "/usr/bin/systemctl",
            "service": "/usr/sbin/service",
            "psql": None,
        }

        def install_effect(call):
            tools["psql"] = "/usr/bin/psql"

        self.runner.expect_stream(
            "env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "update"
        )
        self.runner.expect_stream(
            "env",
            "DEBIAN_FRONTEND=noninteractive",
            "apt-get",
            "install",
            "-y",
            "postgresql",
            effect=install_effect,
        )
        self.runner.expect_stream("systemctl", "start", "postgresql", returncode=1)
        self.runner.expect_stream("service", "postgresql", "start")
        self.runner.expect("runuser", "-u", "postgres", "--", "createuser")

        result = self.make_service(tools).install()

        self.assertEqual(result.warnings, ())
        self.assertEqual(
            self.runner.stream_calls[-2:],
            [
                ("systemctl", "start", "postgresql"),
                ("service", "postgresql", "start"),
            ],
        )

    def test_existing_current_user_role_is_ok(self):
        tools = {
            "apt-get": "/usr/bin/apt-get",
            "runuser": "/usr/sbin/runuser",
            "service": "/usr/sbin/service",
            "psql": None,
        }

        def install_effect(call):
            tools["psql"] = "/usr/bin/psql"

        self.runner.expect_stream(
            "env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "update"
        )
        self.runner.expect_stream(
            "env",
            "DEBIAN_FRONTEND=noninteractive",
            "apt-get",
            "install",
            "-y",
            "postgresql",
            effect=install_effect,
        )
        self.runner.expect_stream("service", "postgresql", "start")
        self.runner.expect(
            "runuser",
            "-u",
            "postgres",
            "--",
            "createuser",
            returncode=1,
            stderr=(
                "createuser: error: creation of new role failed: "
                'ERROR:  role "dev" already exists\n'
            ),
        )

        result = self.make_service(tools).install()

        self.assertEqual(result.manager, "apt-get")
        self.assertEqual(result.warnings, ())

    def test_no_supported_package_manager_is_typed(self):
        with self.assertRaises(PostgresError) as cm:
            self.make_service({}).install_plan()
        self.assertIn("apt-get was not found", cm.exception.message)

    def test_install_failure_is_typed(self):
        tools = {"apt-get": "/usr/bin/apt-get"}
        self.runner.expect_stream(
            "env",
            "DEBIAN_FRONTEND=noninteractive",
            "apt-get",
            "update",
            returncode=1,
        )

        with self.assertRaises(PostgresError) as cm:
            self.make_service(tools).install()

        self.assertIn("could not install PostgreSQL", cm.exception.message)
        self.assertIn("apt-get update", cm.exception.hint)
