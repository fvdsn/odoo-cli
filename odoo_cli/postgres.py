import os
import subprocess


def pg_env(config: dict) -> dict[str, str]:
    """Build environment dict with PG* variables from config."""
    env = dict(os.environ)
    pg = config["postgres"]
    if pg["host"] is not False:
        env["PGHOST"] = str(pg["host"])
    if pg["port"] is not False:
        env["PGPORT"] = str(pg["port"])
    if pg["user"] is not False:
        env["PGUSER"] = str(pg["user"])
    if pg["password"] is not False:
        env["PGPASSWORD"] = str(pg["password"])
    return env


def check_connection(postgres: dict) -> tuple[bool, str]:
    """Try to connect to PostgreSQL with the given settings. Returns (ok, error)."""
    env = pg_env({"postgres": postgres})
    result = subprocess.run(
        ["psql", "-c", "SELECT 1", "postgres"],
        capture_output=True,
        text=True,
        env=env,
        timeout=5,
    )
    if result.returncode == 0:
        return True, ""
    return False, result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "unknown error"


def terminate_connections(config: dict, db_name: str) -> None:
    """Terminate all connections to the given database."""
    env = pg_env(config)
    subprocess.run(
        ["psql", "-d", "postgres", "-c",
         f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
         f"WHERE datname = '{db_name}' AND pid <> pg_backend_pid();"],
        capture_output=True, text=True, env=env,
    )
