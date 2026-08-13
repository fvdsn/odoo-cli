"""`odoo pull`: fast-forward a worktree's checkouts to the latest of what they
track.

Fast-forward-only, per-repo, never interactive (see specs/requirements_v2.md →
"`odoo fetch` and `odoo pull`"). Branches carry no recorded upstream in the
mirror model, so the version a checkout tracks is derived from its branch name
(`infer_base_version`) and fetched from origin by name — reading origin's real
tip without depending on the local mirror.

The fast-forward itself can stream to the terminal (`stream=True`): on a
blobless clone it downloads every changed file, which can take minutes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from odoo_cli.core.models import Workspace, Worktree
from odoo_cli.core.worktrees import infer_base_version
from odoo_cli.util.git import Git

#: Per-checkout outcome status.
ADVANCED = "advanced"
UP_TO_DATE = "up-to-date"
SKIPPED = "skipped"


@dataclass
class CheckoutPull:
    repo: str
    status: str
    detail: str = ""
    #: Source worktree name when this checkout is a symlink into another.
    linked_from: str | None = None


@dataclass
class PullResult:
    worktree: str
    outcomes: list[CheckoutPull] = field(default_factory=list)


class PullService:
    def __init__(self, git: Git):
        self.git = git

    def pull(
        self, workspace: Workspace, worktree: Worktree, *, stream: bool = False
    ) -> PullResult:
        result = PullResult(worktree=worktree.name)
        for child in sorted(worktree.path.iterdir()):
            if not self._is_checkout(workspace, child):
                continue
            linked_from = None
            if child.is_symlink():
                # a linked worktree shares the source's checkout; pulling it
                # advances the source (resolve the symlink and operate there).
                # target is `<source>/<repo>`, so its parent names the source.
                linked_from = child.resolve().parent.name
            result.outcomes.append(
                self._pull_checkout(
                    child.resolve(), child.name, linked_from, stream=stream
                )
            )
        return result

    def _is_checkout(self, workspace: Workspace, child: Path) -> bool:
        """A worktree child backed by a bare repo in `.repositories` (a real
        checkout or a symlink into another worktree's checkout). Plain
        directories — dumps, notes — are ignored."""
        if not (child.is_dir() or child.is_symlink()):
            return False
        return (workspace.repositories_dir / f"{child.name}.git").is_dir()

    def _pull_checkout(
        self, checkout: Path, repo: str, linked_from: str | None, *, stream: bool
    ) -> CheckoutPull:
        def outcome(status: str, detail: str = "") -> CheckoutPull:
            return CheckoutPull(repo, status, detail, linked_from)

        branch = self.git.current_branch(checkout)
        if branch is None:
            return outcome(SKIPPED, "detached HEAD")
        base = infer_base_version(branch)
        if base is None:
            return outcome(
                SKIPPED, f"branch '{branch}' tracks no version; pull/rebase by hand"
            )
        if self.git.is_dirty(checkout):
            return outcome(SKIPPED, "uncommitted changes; commit or stash first")

        fetched = self.git.fetch_branch(checkout, base)
        if fetched.returncode != 0:
            if "couldn't find remote ref" in fetched.stderr:
                return outcome(SKIPPED, f"origin has no '{base}' branch")
            return outcome(SKIPPED, "fetch failed (offline?)")

        # Divergence is decided with plumbing before merging: the merge may be
        # streamed to the terminal (no captured stderr to classify), and this
        # way a merge failure below can only mean the checkout itself died.
        before = self.git.head_commit(checkout)
        target = self.git.commit_of(checkout, "FETCH_HEAD")
        if target is None:
            return outcome(SKIPPED, "fetch failed (offline?)")
        if target == before or self.git.is_ancestor(checkout, target, before):
            return outcome(UP_TO_DATE)
        if not self.git.is_ancestor(checkout, before, target):
            return outcome(
                SKIPPED,
                f"diverged from origin/{base} — run: "
                f"git -C {checkout} pull --rebase origin {base}",
            )
        # On a blobless clone a big fast-forward downloads every changed file;
        # streaming shows git's progress where captured output would sit
        # silent for minutes and invite a Ctrl-C mid-checkout.
        if stream:
            code = self.git.merge_ff_only_streamed(checkout)
        else:
            code = self.git.merge_ff_only(checkout).returncode
        if code != 0:
            return outcome(
                SKIPPED,
                "fast-forward did not finish; the working tree may mix two "
                f"commits — run: git -C {checkout} reset --hard FETCH_HEAD",
            )
        return outcome(ADVANCED, f"{before[:9]}..{target[:9]}")
