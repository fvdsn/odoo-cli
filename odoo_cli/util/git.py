"""Git helpers over the injectable process runner.

Only argv construction and output parsing; policy (which repos, which
branches, blobless or not) belongs to core services.
"""

from __future__ import annotations

from pathlib import Path

from odoo_cli.util.process import ProcessRunner


class Git:
    def __init__(self, runner: ProcessRunner):
        self._runner = runner

    def clone_bare(self, url: str, dest: Path, *, blobless: bool = True) -> None:
        argv: list[str | Path] = ["git", "clone", "--bare"]
        if blobless:
            argv.append("--filter=blob:none")
        argv += [url, dest]
        self._runner.run(argv)

    def fetch(self, repo: Path) -> None:
        """Update a bare repo's local branches from origin."""
        self._runner.run(
            [
                "git",
                "-C",
                repo,
                "fetch",
                "origin",
                "+refs/heads/*:refs/heads/*",
                "--prune",
            ]
        )

    def remote_url(self, repo: Path) -> str | None:
        result = self._runner.run(
            ["git", "-C", repo, "remote", "get-url", "origin"], check=False
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None

    def branch_exists(self, repo: Path, branch: str) -> bool:
        result = self._runner.run(
            ["git", "-C", repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
            check=False,
        )
        return result.returncode == 0

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
