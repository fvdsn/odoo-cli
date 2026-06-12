#!/usr/bin/env bash
# odoo-cli installer, published at https://www.odoo.com/install.sh
#
# Usage:  curl https://www.odoo.com/install.sh | bash
#
# Ensures Python 3.10+ and git (installing them with apt-get or Homebrew when
# missing), downloads the latest odoo-cli-official wheel from PyPI (verified
# against its sha256), unpacks it under ~/.local/share/odoo-cli, writes the
# `odoo` launcher at ~/.local/bin/odoo, then runs `odoo init`. Everything that
# will be installed is announced first; only platform packages are used.
#
# The CLI is pure Python with no dependencies, so installing it is unpacking
# one wheel: no pip, no venv. Re-running the script upgrades in place.
#
# ODOO_CLI_INSTALL_SOURCE overrides the PyPI download with a local checkout
# directory; the e2e tests use it to install from /src.

set -u

SOURCE="${ODOO_CLI_INSTALL_SOURCE:-}"
LIB_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/odoo-cli/lib"
BIN_DIR="$HOME/.local/bin"
# `odoo init` needs more than the interpreter: git for the clones, the venv
# module (a separate package on Debian/Ubuntu), and the headers Odoo's own
# requirements compile against.
APT_PACKAGES="git python3 python3-venv python3-dev
    build-essential libpq-dev libldap2-dev libsasl2-dev"

say()  { printf '%s\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

python_ok() {
    "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' \
        2>/dev/null
}

find_python() {
    local candidate
    for candidate in python3 python3.14 python3.13 python3.12 python3.11 python3.10; do
        if command -v "$candidate" >/dev/null 2>&1 && python_ok "$candidate"; then
            command -v "$candidate"
            return 0
        fi
    done
    return 1
}

apt_prefix() {
    if [ "$(id -u)" = 0 ]; then
        echo ""
    elif command -v sudo >/dev/null 2>&1; then
        echo "sudo"
    else
        fail "administrator privileges are needed to install packages;" \
            "install sudo or run as root, then re-run"
    fi
}

apt_is_complete() {
    find_python >/dev/null || return 1
    command -v git >/dev/null 2>&1 || return 1
    "$(find_python)" -m ensurepip --version >/dev/null 2>&1 || return 1
    dpkg -s python3-dev build-essential libpq-dev libldap2-dev libsasl2-dev \
        >/dev/null 2>&1 || return 1
}

setup_linux() {
    if apt_is_complete; then
        return 0
    fi
    command -v apt-get >/dev/null 2>&1 \
        || fail "Python 3.10+ is missing and apt-get was not found;" \
            "install Python 3.10+ and git manually, then re-run"
    local sudo_cmd
    sudo_cmd=$(apt_prefix) || exit 1
    say "Installing with apt-get${sudo_cmd:+ (sudo may ask for your password)}:"
    # shellcheck disable=SC2086
    say "   " $APT_PACKAGES
    $sudo_cmd env DEBIAN_FRONTEND=noninteractive apt-get update \
        || fail "apt-get update failed"
    # shellcheck disable=SC2086
    $sudo_cmd env DEBIAN_FRONTEND=noninteractive apt-get install -y \
        $APT_PACKAGES || fail "apt-get install failed"
}

setup_macos() {
    if find_python >/dev/null && command -v git >/dev/null 2>&1; then
        return 0
    fi
    command -v brew >/dev/null 2>&1 \
        || fail "Python 3.10+ is missing and Homebrew was not found;" \
            "install it from https://brew.sh, then re-run"
    say "Installing with Homebrew: python git"
    brew install python git || fail "brew install failed"
}

# Fetch the latest wheel from PyPI, check its sha256, and unpack it (a wheel
# is a zip of the pure-Python package) into $LIB_DIR.
fetch_from_pypi() {
    local python=$1
    "$python" - "$LIB_DIR" <<'PYEOF'
import hashlib
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

lib = Path(sys.argv[1])
with urllib.request.urlopen(
    "https://pypi.org/pypi/odoo-cli-official/json", timeout=30
) as response:
    meta = json.load(response)
wheels = [u for u in meta["urls"] if u["filename"].endswith("py3-none-any.whl")]
if not wheels:
    raise SystemExit(f"no wheel published for odoo-cli-official {meta['info']['version']}")
wheel = wheels[0]
print(f"Downloading odoo-cli-official {meta['info']['version']} from PyPI...")
with urllib.request.urlopen(wheel["url"], timeout=60) as response:
    data = response.read()
digest = hashlib.sha256(data).hexdigest()
if digest != wheel["digests"]["sha256"]:
    raise SystemExit(f"checksum mismatch for {wheel['filename']}")
with zipfile.ZipFile(io.BytesIO(data)) as archive:
    archive.extractall(lib)
PYEOF
}

main() {
    case "$(uname -s)" in
        Linux) setup_linux ;;
        Darwin) setup_macos ;;
        *) fail "unsupported platform $(uname -s); install Python 3.10+," \
            "then \`pip install odoo-cli-official\` and \`odoo init\`" ;;
    esac

    local python
    python=$(find_python) \
        || fail "Python 3.10+ is still not available after installation"
    say "Using $python ($("$python" --version 2>&1))"

    rm -rf "$LIB_DIR"
    mkdir -p "$LIB_DIR"
    if [ -n "$SOURCE" ]; then
        say "Installing odoo-cli from $SOURCE..."
        cp -R "$SOURCE/odoo_cli" "$LIB_DIR/" \
            || fail "could not copy odoo_cli from $SOURCE"
    else
        fetch_from_pypi "$python" || fail "could not download odoo-cli from PyPI"
    fi

    mkdir -p "$BIN_DIR"
    # a sys.path launcher instead of PYTHONPATH: the CLI's own subprocesses
    # (odoo-bin, pip in the Odoo venvs) must not inherit our import path
    cat > "$BIN_DIR/odoo" <<LAUNCHER
#!$python
import sys

sys.path.insert(0, "$LIB_DIR")
from odoo_cli.cli.main import main

if __name__ == "__main__":
    main()
LAUNCHER
    chmod +x "$BIN_DIR/odoo"
    say "Installed the odoo command at $BIN_DIR/odoo"
    case ":$PATH:" in
        *":$BIN_DIR:"*) ;;
        *) warn "$BIN_DIR is not on your PATH; add it to your shell profile:" \
            "export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
    esac

    say "Setting up the Odoo workspace (this installs PostgreSQL if missing)..."
    "$BIN_DIR/odoo" init || fail "odoo init failed"
}

# main is only reached once the whole script is downloaded, and /dev/null on
# stdin keeps children from consuming the piped script.
main "$@" </dev/null
