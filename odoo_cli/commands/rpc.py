import json
import sys
import urllib.request
import urllib.error

import typer

from odoo_cli.console import console
from odoo_cli.workspace import find_workspace_root, load_required_config


def _jsonrpc(url: str, method: str, params: dict) -> dict:
    """Make a JSON-RPC call."""
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }).encode()

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def _authenticate(base_url: str, db: str, login: str, password: str) -> int:
    """Authenticate and return the user ID."""
    result = _jsonrpc(f"{base_url}/jsonrpc", "call", {
        "service": "common",
        "method": "authenticate",
        "args": [db, login, password, {}],
    })
    uid = result.get("result")
    if not uid:
        error = result.get("error", {}).get("data", {}).get("message", "Authentication failed")
        raise RuntimeError(error)
    return uid


def rpc(
    call: str = typer.Argument(
        ...,
        help='JSON-RPC call: {"model": "res.partner", "method": "search_read", "args": [[]], "kwargs": {"fields": ["name"], "limit": 5}}',
    ),
) -> None:
    """Execute an RPC call on the Odoo server and output JSON."""
    directory = find_workspace_root()
    if directory is None:
        console.print(
            "[red]No config.toml found in this directory or its parents. Run 'odoo-cli init' first.[/red]",
            file=sys.stderr,
        )
        raise typer.Exit(code=1)
    config = load_required_config(directory)

    odoo_config = config.get("odoo", {})
    pg = config["postgres"]
    http_port = odoo_config.get("http_port", 8069)
    base_url = f"http://localhost:{http_port}"
    db = pg["db_name"]
    login = odoo_config.get("admin_user", "admin")
    password = odoo_config.get("admin_password", "admin")

    try:
        params = json.loads(call)
    except json.JSONDecodeError as e:
        print(f'{{"error": "Invalid JSON: {e}"}}', file=sys.stderr)
        raise typer.Exit(code=1)

    model = params.get("model")
    method = params.get("method")
    args = params.get("args", [])
    kwargs = params.get("kwargs", {})

    if not model or not method:
        print('{"error": "Required fields: model, method"}', file=sys.stderr)
        raise typer.Exit(code=1)

    try:
        uid = _authenticate(base_url, db, login, password)

        result = _jsonrpc(f"{base_url}/jsonrpc", "call", {
            "service": "object",
            "method": "execute_kw",
            "args": [db, uid, password, model, method, args, kwargs],
        })

        if "error" in result:
            error_msg = result["error"].get("data", {}).get("message", str(result["error"]))
            print(json.dumps({"error": error_msg}))
            raise typer.Exit(code=1)

        print(json.dumps(result.get("result"), indent=2))

    except urllib.error.URLError:
        print('{"error": "Cannot connect to Odoo server. Is it running?"}', file=sys.stderr)
        raise typer.Exit(code=1)
    except RuntimeError as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        raise typer.Exit(code=1)
