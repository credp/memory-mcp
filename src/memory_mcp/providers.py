from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Protocol

from .errors import RepositoryError


class ReviewProvider(Protocol):
    name: str

    def open_review(
        self, worktree: Path, *, base: str, head: str, title: str, body: str
    ) -> str: ...


class GitHubCliProvider:
    """Open a GitHub pull request through an installation-scoped gh identity."""

    name = "github"

    def open_review(
        self, worktree: Path, *, base: str, head: str, title: str, body: str
    ) -> str:
        try:
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "create",
                    "--base",
                    base,
                    "--head",
                    head,
                    "--title",
                    title,
                    "--body",
                    body,
                ],
                cwd=worktree,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RepositoryError(f"GitHub pull-request creation failed: {exc}") from exc
        if result.returncode != 0:
            message = result.stderr.strip() or "unknown gh error"
            raise RepositoryError(f"GitHub pull-request creation failed: {message}")
        url = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
        if not url.startswith("https://github.com/"):
            raise RepositoryError("GitHub pull-request creation returned no GitHub URL")
        return url
