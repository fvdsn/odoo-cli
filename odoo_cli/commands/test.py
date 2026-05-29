import re
import subprocess

import typer

from odoo_cli.console import console
from odoo_cli.odoo import configured_addons_paths, current_workspace
from odoo_cli.postgres import pg_env, terminate_connections


def test(
    modules: str | None = typer.Argument(
        None,
        help="Comma-separated modules to test (default: all installed).",
    ),
    tags: str | None = typer.Option(
        None,
        "--tags",
        "-t",
        help="Test tags to filter (e.g. 'test_sale', '-at_install,post_install').",
    ),
    keep_db: bool = typer.Option(
        False,
        "--keep-db",
        help="Keep the test database after running tests.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show full Odoo test output.",
    ),
) -> None:
    """Run Odoo tests on a dedicated test database."""
    workspace = current_workspace(require_odoo=True, require_venv=True)
    directory = workspace.directory
    config = workspace.config

    odoo_config = workspace.odoo_config
    db_name = f"{workspace.database_name}-test"
    env = pg_env(config)

    # Create fresh test database
    terminate_connections(config, db_name)
    subprocess.run(
        ["dropdb", "--if-exists", db_name],
        capture_output=True,
        text=True,
        env=env,
    )
    console.print(f"  Creating test database [bold]{db_name}[/bold]...", end=" ")
    result = subprocess.run(
        ["createdb", db_name],
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        console.print("[red]failed[/red]")
        console.print(f"    [dim]{result.stderr.strip()}[/dim]")
        raise typer.Exit(code=1)
    console.print("[green]done[/green]")

    # Build test command
    target_modules = modules
    if not target_modules:
        installed = odoo_config.get("install_modules", [])
        target_modules = ",".join(installed) if installed else "base"

    addons_paths = [str(path) for path in configured_addons_paths(directory, config)]

    cmd = workspace.command(
        f"--addons-path={','.join(addons_paths)}",
        "-d",
        db_name,
        "-i",
        target_modules,
        "--stop-after-init",
        "--no-http",
        "--http-port=0",
        "--without-demo",
        "--log-level=test",
    )

    # --test-enable is always needed to run tests during module installation.
    cmd.append("--test-enable")

    if tags:
        # Resolve bare tags into Odoo's tag format: [-][tag][/module][:class][.method]
        # A bare name like "test_foo" becomes "/{module}:.test_foo" to match by method.
        # A class.method like "TestFoo.test_bar" becomes "/{module}:TestFoo.test_bar".
        # Already-qualified tags (containing / or :) are passed through.
        resolved_parts = []
        for t in tags.split(","):
            t = t.strip()
            if "/" in t or ":" in t:
                resolved_parts.append(t)
            elif "." in t:
                resolved_parts.append(f"/{target_modules}:{t}")
            else:
                resolved_parts.append(f"/{target_modules}:.{t}")
        cmd.extend(["--test-tags", ",".join(resolved_parts)])

    console.print(f"  Running tests for [bold]{target_modules}[/bold]...")
    console.print(f"  [dim]$ {' '.join(cmd)}[/dim]\n")

    if verbose:
        result = subprocess.run(cmd)
        exit_code = result.returncode
    else:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        failures = []
        errors = []
        current_block: list[str] = []
        in_error_block = False
        summary_line = ""
        tests_run = 0

        for line in proc.stdout:
            line = line.rstrip()

            # Track module loading progress
            m = re.search(r"Loading module (\w+)", line)
            if m:
                console.print(f"  [dim]Loading {m.group(1)}...[/dim]")
                continue

            # Print a dot per test to show progress
            if " Starting " in line and "..." in line:
                tests_run += 1
                if tests_run % 50 == 0:
                    console.print(f"  [dim]{tests_run} tests...[/dim]")
                continue

            # Capture Odoo's own summary (e.g. "1 failed, 5 error(s) of 899 tests")
            if re.search(r"\d+ (failed|error).* of \d+ tests", line):
                summary_line = line

            # Detect test failure/error block start
            # Matches lines like "... FAIL: TestFoo.test_bar" or "... ERROR: TestFoo.test_bar"
            if re.search(r" (FAIL|ERROR): \w+\.\w+", line):
                in_error_block = True
                current_block = [line]
                continue

            if in_error_block:
                current_block.append(line)
                # A new log timestamp line ends the block
                if line and re.match(r"\d{4}-\d{2}-\d{2}", line):
                    block_text = "\n".join(current_block[:-1])
                    if " FAIL: " in current_block[0]:
                        failures.append(block_text)
                    else:
                        errors.append(block_text)
                    in_error_block = False
                    current_block = []
                continue

        # Flush remaining block
        if in_error_block and current_block:
            block_text = "\n".join(current_block)
            if " FAIL:" in current_block[0]:
                failures.append(block_text)
            else:
                errors.append(block_text)

        proc.wait()
        exit_code = proc.returncode

        # Print failures and errors
        if failures:
            console.print(f"\n[red bold]Failures ({len(failures)}):[/red bold]")
            for f in failures:
                console.print(f"[red]{f}[/red]")

        if errors:
            console.print(f"\n[red bold]Errors ({len(errors)}):[/red bold]")
            for e in errors:
                console.print(f"[red]{e}[/red]")

        # Print Odoo's summary
        if summary_line:
            console.print(f"\n  [bold]{summary_line}[/bold]")

    # Cleanup
    if not keep_db:
        terminate_connections(config, db_name)
        subprocess.run(
            ["dropdb", "--if-exists", db_name],
            capture_output=True,
            text=True,
            env=env,
        )
        console.print(f"  Dropped test database [dim]{db_name}[/dim]")
    else:
        console.print(f"  Test database [dim]{db_name}[/dim] kept for inspection.")

    if exit_code != 0:
        console.print("\n[red]Tests failed.[/red]")
        raise typer.Exit(code=exit_code)

    console.print("\n[green]Tests passed.[/green]")
