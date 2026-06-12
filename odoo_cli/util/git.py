"""Git helpers over the injectable process runner.

Only argv construction and output parsing; policy (which repos, which
branches, blobless or not) belongs to core services.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from odoo_cli.util.process import ProcessRunner

MIN_BLOBLESS_GIT_VERSION = (2, 40, 0)


class Git:
    def __init__(self, runner: ProcessRunner):
        self._runner = runner

    def version(self) -> tuple[int, int, int] | None:
        result = self._runner.run(["git", "--version"], check=False)
        if result.returncode != 0:
            return None
        for part in result.stdout.split():
            bits = part.split(".")
            if len(bits) < 2:
                continue
            numbers = []
            for bit in bits[:3]:
                if not bit.isdigit():
                    break
                numbers.append(int(bit))
            if len(numbers) >= 2:
                while len(numbers) < 3:
                    numbers.append(0)
                return tuple(numbers[:3])
        return None

    def supports_reliable_blobless_clone(self) -> bool:
        version = self.version()
        return version is not None and version >= MIN_BLOBLESS_GIT_VERSION

    def clone_bare(self, url: str, dest: Path, *, blobless: bool = True) -> None:
        argv: list[str | Path] = ["git", "clone", "--bare"]
        if blobless:
            argv.append("--filter=blob:none")
        argv += [url, dest]
        self._runner.run(argv)

    def fetch(self, repo: Path, *, exclude_branches: Iterable[str] = ()) -> None:
        """Update a bare repo's local branches from origin.

        `exclude_branches` (negative refspecs, git >= 2.29) must list the
        branches checked out in attached worktrees: git refuses to update
        those and aborts the whole fetch. No --prune: local-only branches
        (worktree feature branches) are never deleted by a fetch.
        """
        argv: list[str | Path] = [
            "git",
            "-C",
            repo,
            "fetch",
            "origin",
            "+refs/heads/*:refs/heads/*",
        ]
        argv += [f"^refs/heads/{branch}" for branch in exclude_branches]
        self._runner.run(argv)

    def config_get(self, repo: Path, key: str) -> str | None:
        result = self._runner.run(
            ["git", "-C", repo, "config", "--get", key], check=False
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None

    def is_partial_clone(self, repo: Path) -> bool:
        return (
            self.config_get(repo, "remote.origin.promisor") == "true"
            or self.config_get(repo, "remote.origin.partialclonefilter") is not None
        )

    def remote_url(self, repo: Path) -> str | None:
        result = self._runner.run(
            ["git", "-C", repo, "remote", "get-url", "origin"], check=False
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None

    def has_valid_head(self, repo: Path) -> bool:
        """False for a directory that is not a repository or whose HEAD does
        not resolve — the signature of a clone that died mid-transfer (git
        writes the refs only after fetching the objects)."""
        result = self._runner.run(
            ["git", "-C", repo, "rev-parse", "--verify", "--quiet", "HEAD"],
            check=False,
        )
        return result.returncode == 0

    def branch_exists(self, repo: Path, branch: str) -> bool:
        result = self._runner.run(
            ["git", "-C", repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
            check=False,
        )
        return result.returncode == 0

    def default_branch(self, repo: Path) -> str:
        result = self._runner.run(
            ["git", "-C", repo, "symbolic-ref", "--short", "HEAD"]
        )
        return result.stdout.strip()

    def current_branch(self, checkout: Path) -> str | None:
        """Checked-out branch of a working tree; None when HEAD is detached."""
        result = self._runner.run(
            ["git", "-C", checkout, "symbolic-ref", "--quiet", "--short", "HEAD"],
            check=False,
        )
        branch = result.stdout.strip()
        return branch if result.returncode == 0 and branch else None

    def head_commit(self, checkout: Path) -> str:
        result = self._runner.run(["git", "-C", checkout, "rev-parse", "HEAD"])
        return result.stdout.strip()

    def list_branches(self, repo: Path) -> list[str]:
        result = self._runner.run(
            ["git", "-C", repo, "for-each-ref", "refs/heads", "--format=%(refname:short)"]
        )
        return [line for line in result.stdout.splitlines() if line]

    def worktree_add(
        self,
        repo: Path,
        dest: Path,
        branch: str,
        *,
        new_branch_from: str | None = None,
    ) -> None:
        argv: list[str | Path] = ["git", "-C", repo, "worktree", "add"]
        if new_branch_from:
            argv += ["-b", branch, dest, new_branch_from]
        else:
            argv += [dest, branch]
        self._runner.run(argv)

    def common_dir(self, checkout: Path) -> Path | None:
        """The git common dir of a checkout (the backing repository), or None
        when the path is not a usable git checkout."""
        result = self._runner.run(
            ["git", "-C", checkout, "rev-parse", "--git-common-dir"],
            check=False,
        )
        if result.returncode != 0:
            return None
        raw = result.stdout.strip()
        if not raw:
            return None
        path = Path(raw)
        if not path.is_absolute():
            path = checkout / path
        return path.resolve()

    def worktree_prune(self, repo: Path) -> None:
        self._runner.run(["git", "-C", repo, "worktree", "prune"])

    def worktree_paths(self, repo: Path) -> list[Path]:
        result = self._runner.run(["git", "-C", repo, "worktree", "list", "--porcelain"])
        paths = []
        for line in result.stdout.splitlines():
            if line.startswith("worktree "):
                paths.append(Path(line.removeprefix("worktree ")))
        return paths

    def worktree_branches(self, repo: Path) -> list[str]:
        """Branches checked out in worktrees attached to this repository."""
        result = self._runner.run(["git", "-C", repo, "worktree", "list", "--porcelain"])
        branches = []
        for line in result.stdout.splitlines():
            if line.startswith("branch refs/heads/"):
                branches.append(line.removeprefix("branch refs/heads/"))
        return branches
