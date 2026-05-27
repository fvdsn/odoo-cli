import re
import subprocess
from pathlib import Path

from odoo_cli.console import console

REPOS = {
    "odoo": "git@github.com:odoo/odoo.git",
    "enterprise": "git@github.com:odoo/enterprise.git",
    "documentation": "git@github.com:odoo/documentation.git",
    "themes": "git@github.com:odoo/design-themes.git",
}

DEV_REMOTE_URL = "git@github.com:odoo-dev/{repo}.git"

DEFAULT_VERSIONS = ["master", "19.0", "18.0"]


def get_available_versions() -> list[str]:
    """Fetch version branches from the odoo remote."""
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--heads", REPOS["odoo"]],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return DEFAULT_VERSIONS
        branches = set()
        for line in result.stdout.splitlines():
            ref = line.split("refs/heads/")[-1]
            if not ref.startswith("tmp."):
                branches.add(ref)

        def numeric_tuple(s):
            return tuple(
                int(part) if part.isdigit() else part
                for part in re.split(r"(\d+)", s)
            )

        def negate_tuple(t):
            return tuple(-x if isinstance(x, int) else x for x in t)

        def sort_key(b):
            if b == "master":
                return (0,)
            if b.startswith("staging."):
                return (2, negate_tuple(numeric_tuple(b)))
            return (1, negate_tuple(numeric_tuple(b)))

        return sorted(branches, key=sort_key)
    except (subprocess.TimeoutExpired, Exception):
        return DEFAULT_VERSIONS


def major_version(branch: str) -> str | None:
    """Extract the major version from a branch name, e.g. 'saas-17.3' -> '17.0'."""
    m = re.search(r"(\d+)\.", branch)
    if m:
        return f"{m.group(1)}.0"
    return None


def branch_exists(url: str, branch: str) -> bool:
    """Check if a branch exists on a remote."""
    result = subprocess.run(
        ["git", "ls-remote", "--heads", url, branch],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and branch in result.stdout


def resolve_branch(url: str, branch: str) -> str | None:
    """Check if branch exists on remote; if not, fall back to major version.

    Returns the resolved branch name, or None if neither the branch
    nor its major version fallback exist.
    """
    if branch_exists(url, branch):
        return branch

    fallback = major_version(branch)
    if fallback and fallback != branch and branch_exists(url, fallback):
        return fallback

    return None


def repo_name_from_url(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")


def get_repos(directory: Path, config: dict) -> list[tuple[str, str, Path]]:
    """Return list of (name, url, dest) for all configured repos."""
    repos = [("odoo", REPOS["odoo"], directory / "odoo")]
    if config["repositories"]["enterprise"]:
        repos.append(("enterprise", REPOS["enterprise"], directory / "enterprise"))
    if config["repositories"]["documentation"]:
        repos.append(("documentation", REPOS["documentation"], directory / "documentation"))
    if config["repositories"]["themes"]:
        repos.append(("themes", REPOS["themes"], directory / "themes"))

    addons_dir = directory / "addons"
    for url in config["repositories"].get("extra_addons", []):
        name = repo_name_from_url(url)
        repos.append((name, url, addons_dir / name))

    return repos


def is_feature_branch(branch: str) -> bool:
    """Return True if the branch looks like a feature branch (not a version branch)."""
    if branch == "master":
        return False
    if re.fullmatch(r"\d+\.\d+", branch):
        return False
    if re.fullmatch(r"saas-\d+(\.\d+)?", branch):
        return False
    if re.fullmatch(r"staging\..+", branch):
        return False
    return True


def get_repo_status(dest: Path) -> dict:
    """Check a repo's working tree status: current branch, dirty state, ahead commits."""
    branch = subprocess.run(
        ["git", "-C", str(dest), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True,
    ).stdout.strip()

    dirty = subprocess.run(
        ["git", "-C", str(dest), "status", "--porcelain"],
        capture_output=True, text=True,
    ).stdout.strip() != ""

    # Check if branch has unpushed commits
    ahead = 0
    result = subprocess.run(
        ["git", "-C", str(dest), "rev-list", "--count", f"origin/{branch}..HEAD"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        ahead = int(result.stdout.strip())

    return {"branch": branch, "dirty": dirty, "ahead": ahead}


def check_repos_before_switch(
    directory: Path, config: dict,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]], list[tuple[str, int]]]:
    """Check all repos for blockers and warnings before version switch.

    Returns (dirty_repos, feature_branch_repos, unpushed_repos) where each
    is a list of (repo_name, detail).
    """
    repos = get_repos(directory, config)

    dirty: list[tuple[str, str]] = []
    on_feature_branch: list[tuple[str, str]] = []
    unpushed: list[tuple[str, int]] = []

    for name, _url, dest in repos:
        if not dest.exists():
            continue
        status = get_repo_status(dest)
        if status["dirty"]:
            dirty.append((name, status["branch"]))
        if is_feature_branch(status["branch"]):
            on_feature_branch.append((name, status["branch"]))
        if status["ahead"] > 0:
            unpushed.append((name, status["ahead"]))

    return dirty, on_feature_branch, unpushed


def checkout_version(directory: Path, config: dict, version: str) -> None:
    """Checkout a version branch across all configured repos, with fallback."""
    repos = get_repos(directory, config)

    for name, url, dest in repos:
        if not dest.exists():
            console.print(f"  [yellow]{name}/[/yellow] not found, skipping.")
            continue

        actual_branch = resolve_branch(url, version)
        if actual_branch is None:
            console.print(f"  [red]{name}: no valid branch for '{version}', skipping.[/red]")
            continue
        if actual_branch != version:
            console.print(
                f"  [yellow]{name}: branch '{version}' not found, "
                f"falling back to '{actual_branch}'[/yellow]"
            )

        console.print(f"  Checking out [bold]{name}[/bold] → [dim]{actual_branch}[/dim]")
        result = subprocess.run(
            ["git", "-C", str(dest), "fetch", "origin", actual_branch],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            console.print(f"  [red]{name}: failed to fetch '{actual_branch}'[/red]")
            continue

        result = subprocess.run(
            ["git", "-C", str(dest), "checkout", actual_branch],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            console.print(f"  [red]{name}: failed to checkout '{actual_branch}'[/red]")
            continue
