#!/usr/bin/env bash
# odoo-cli installer, published at https://www.odoo.com/install.sh
#
# Usage:  curl https://www.odoo.com/install.sh | bash
#
# Ensures Python 3.10+ and git (installing them with apt-get or Homebrew when
# missing), downloads the latest odoo-cli-official wheel from PyPI (verified
# against its sha256), unpacks it under ~/.local/share/Odoo/cli, writes the
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
# Live next to Odoo's own data dir (appdirs uses ~/.local/share/Odoo on Linux).
LIB_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/Odoo/cli"
BIN_DIR="$HOME/.local/bin"
# `odoo init` needs more than the interpreter: the venv module (a separate
# package on Debian/Ubuntu) and the headers Odoo's own requirements compile
# against (the venvs don't use system site-packages, so psycopg2/lxml/python-ldap
# build from source). These are checked one by one with `dpkg -s` so we install
# only the ones actually missing; python3 and git are handled separately because
# a non-apt interpreter or git (pyenv, /usr/local) is perfectly fine.
APT_DEV_PACKAGES="python3-venv python3-dev build-essential
    libpq-dev libldap2-dev libsasl2-dev"

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

# List the apt packages still needed, one per line (empty when nothing is
# missing). A missing interpreter pulls in python3 plus its venv/headers; git
# only when no git is on PATH; the dev packages whenever `dpkg -s` can't find
# them. The caller de-duplicates, so naming python3-venv/python3-dev twice is
# fine.
apt_missing() {
    local pkg
    if ! find_python >/dev/null; then
        printf '%s\n' python3 python3-venv python3-dev
    fi
    command -v git >/dev/null 2>&1 || printf '%s\n' git
    # shellcheck disable=SC2086
    for pkg in $APT_DEV_PACKAGES; do
        dpkg -s "$pkg" >/dev/null 2>&1 || printf '%s\n' "$pkg"
    done
}

setup_linux() {
    local missing
    missing=$(apt_missing | sort -u | tr '\n' ' ')
    missing=${missing% }
    [ -z "$missing" ] && return 0  # every prerequisite already present
    command -v apt-get >/dev/null 2>&1 \
        || fail "missing prerequisites ($missing) and apt-get was not found;" \
            "install Python 3.10+ and git manually, then re-run"
    local sudo_cmd
    sudo_cmd=$(apt_prefix) || exit 1
    say "Installing with apt-get${sudo_cmd:+ (sudo may ask for your password)}:"
    say "    $missing"
    $sudo_cmd env DEBIAN_FRONTEND=noninteractive apt-get update \
        || fail "apt-get update failed"
    # shellcheck disable=SC2086
    $sudo_cmd env DEBIAN_FRONTEND=noninteractive apt-get install -y \
        $missing || fail "apt-get install failed"
}

# Blobless clones (used by `odoo init`) are only reliable on git >= 2.40;
# older git silently forces a full clone of Odoo, which is slow and
# network-fragile. On macOS brew can provide a current git, so treat an old
# git like a missing prerequisite (Apple's CLT git lags well behind 2.40).
GIT_MIN_MINOR=40

git_recent() {
    command -v git >/dev/null 2>&1 || return 1
    local version major minor
    version=$(git --version 2>/dev/null | awk '{print $3}')
    major=${version%%.*}
    minor=${version#*.}
    minor=${minor%%.*}
    case "$major" in ''|*[!0-9]*) return 1 ;; esac
    case "$minor" in ''|*[!0-9]*) return 1 ;; esac
    [ "$major" -gt 2 ] && return 0
    [ "$major" -eq 2 ] && [ "$minor" -ge "$GIT_MIN_MINOR" ]
}

setup_macos() {
    # Install only what is missing: a Python 3.10+ and a git new enough for
    # blobless clones. A present-but-old git must still be upgraded, so this
    # checks the version, not just `command -v git`.
    local need="" missing=""
    if ! find_python >/dev/null; then
        need="python"
        missing="Python 3.10+"
    fi
    if ! git_recent; then
        need="${need:+$need }git"
        missing="${missing:+$missing and }git >= 2.$GIT_MIN_MINOR"
    fi
    [ -z "$need" ] && return 0
    command -v brew >/dev/null 2>&1 \
        || fail "missing $missing, and Homebrew was not found;" \
            "install Homebrew from https://brew.sh, then re-run"
    say "Installing with Homebrew: $need"
    # shellcheck disable=SC2086
    brew install $need || fail "brew install failed"
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

# Make `odoo` work in new terminals without the user touching anything: append
# the PATH export to their shell's login profile, guarded by a marker so re-runs
# never duplicate it. ~/.local/bin is the standard user bin dir; some systems
# (Debian's ~/.profile) already add it, in which case we do nothing.
ensure_on_path() {
    case ":$PATH:" in
        *":$BIN_DIR:"*) return 0 ;;  # already on PATH, nothing to do
    esac
    local rc marker
    case "$(basename "${SHELL:-sh}")" in
        zsh)  rc="$HOME/.zprofile" ;;   # sourced by every login zsh (macOS, …)
        bash) rc="$HOME/.bashrc" ;;     # sourced by interactive bash
        *)    rc="$HOME/.profile" ;;
    esac
    marker="# added by odoo-cli installer"
    if [ -f "$rc" ] && grep -qF "$marker" "$rc"; then
        return 0  # a previous run already added it
    fi
    if printf '\n# Make the odoo command available\nexport PATH="$HOME/.local/bin:$PATH"  %s\n' \
        "$marker" >> "$rc"; then
        say "Added $BIN_DIR to your PATH in $rc"
        say "   Open a new terminal, or run: source $rc"
    else
        warn "could not update $rc; add this to your shell profile yourself:" \
            "export PATH=\"\$HOME/.local/bin:\$PATH\""
    fi
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
    ensure_on_path

    say "Setting up the Odoo workspace (this installs PostgreSQL if missing)..."
    "$BIN_DIR/odoo" init || fail "odoo init failed"
}

# main is only reached once the whole script is downloaded, and /dev/null on
# stdin keeps children from consuming the piped script.
main "$@" </dev/null
