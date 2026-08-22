from __future__ import annotations

import re
import secrets
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePath
from typing import Any

from .errors import InvalidPathError, MemoryError, RepositoryError
from .providers import ReviewProvider


MAX_PROPOSAL_BYTES = 2 * 1024 * 1024
SAFE_REF = re.compile(r"^[A-Za-z0-9._/-]+$")
SENSITIVE = {
    "authorization_header": re.compile(r"(?i)authorization[\" '\t:=]+(?:bearer|basic)"),
    "credential_assignment": re.compile(
        r"(?i)(api[_-]?key|access[_-]?token|password|secret)"
        r"[\" '\t]*[:=][ \t]*(?![\"']?<redacted>[\"']?(?:\s|[,;}]|$))"
        r"[^\s,;}]{8,}"
    ),
    "private_key": re.compile(r"-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----"),
}


class ProposalService:
    def __init__(
        self,
        root: Path,
        provider: ReviewProvider,
        *,
        remote: str = "origin",
        base_branch: str = "main",
        branch_prefix: str = "memory-proposal",
    ):
        self.root = root
        self.provider = provider
        for value, label in (
            (remote, "remote"),
            (base_branch, "base branch"),
            (branch_prefix, "branch prefix"),
        ):
            if (
                not value
                or value.startswith("-")
                or value.startswith("/")
                or not SAFE_REF.fullmatch(value)
                or ".." in value
            ):
                raise MemoryError(f"Invalid proposal {label}")
        self.remote = remote
        self.base_branch = base_branch
        self.branch_prefix = branch_prefix.rstrip("/")
        if not self.branch_prefix:
            raise MemoryError("Invalid proposal branch prefix")

    def _git(self, cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(
                ["git", "-C", str(cwd), "--literal-pathspecs", *args],
                text=True, encoding="utf-8", errors="replace", capture_output=True,
                timeout=60, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RepositoryError(f"Git command failed: {exc}") from exc
        if check and result.returncode != 0:
            raise RepositoryError(
                f"Git command failed: {result.stderr.strip() or 'unknown Git error'}"
            )
        return result

    def _require_clean(self) -> None:
        if self._git(self.root, "status", "--porcelain").stdout.strip():
            raise RepositoryError("Proposal repository must have a clean working tree")

    def refresh(self) -> dict[str, Any]:
        self._require_clean()
        branch = self._git(self.root, "branch", "--show-current").stdout.strip()
        if branch != self.base_branch:
            raise RepositoryError(f"Repository must be on {self.base_branch}")
        before = self._git(self.root, "rev-parse", "HEAD").stdout.strip()
        self._git(self.root, "fetch", "--prune", self.remote, self.base_branch)
        self._git(self.root, "merge", "--ff-only", f"{self.remote}/{self.base_branch}")
        after = self._git(self.root, "rev-parse", "HEAD").stdout.strip()
        return {"before": before, "after": after, "changed": before != after}

    def _validate_path(self, value: str) -> PurePath:
        if not value or len(value.encode("utf-8")) > 512:
            raise InvalidPathError("Proposal path must be between 1 and 512 bytes")
        path = PurePath(value)
        if (
            path.is_absolute()
            or ".." in path.parts
            or not path.parts
            or any(part in {"", "."} for part in path.parts)
        ):
            raise InvalidPathError("Proposal path must be repository-relative")
        if path.suffix.lower() != ".md":
            raise InvalidPathError("Proposal path must be a Markdown file")
        if path.parts[0] == ".github" or any(part == ".git" for part in path.parts):
            raise InvalidPathError("Proposal path is protected")
        return path

    def propose_memory(
        self,
        *,
        path: str,
        content: str,
        title: str,
        rationale: str,
        source_run_id: str = "",
    ) -> dict[str, Any]:
        relative = self._validate_path(path)
        encoded = content.encode("utf-8")
        if not content.strip() or len(encoded) > MAX_PROPOSAL_BYTES:
            raise MemoryError("Proposal content must be non-empty and at most 2 MiB")
        if not title.strip() or len(title) > 200 or "\n" in title:
            raise MemoryError("Proposal title must be one line of at most 200 characters")
        if not rationale.strip() or len(rationale) > 4000:
            raise MemoryError("Proposal rationale must be between 1 and 4000 characters")
        if len(source_run_id) > 200 or "\n" in source_run_id:
            raise MemoryError("Source run ID must be one line of at most 200 characters")
        outbound = "\n".join((content, title, rationale, source_run_id))
        hits = sorted(name for name, pattern in SENSITIVE.items() if pattern.search(outbound))
        if hits:
            raise MemoryError("Proposal rejected: credential-shaped content detected")

        self._require_clean()
        self._git(self.root, "fetch", "--prune", self.remote, self.base_branch)
        base_ref = f"{self.remote}/{self.base_branch}"
        base_commit = self._git(self.root, "rev-parse", base_ref).stdout.strip()
        now = datetime.now(timezone.utc)
        branch = (
            f"{self.branch_prefix}/{now.strftime('%Y%m%dT%H%M%SZ')}-"
            f"{secrets.token_hex(4)}"
        )
        temporary = Path(tempfile.mkdtemp(prefix="memory-mcp-proposal-"))
        added = False
        try:
            self._git(self.root, "worktree", "add", "--detach", str(temporary), base_ref)
            added = True
            self._git(temporary, "switch", "-c", branch)
            target = temporary.joinpath(*relative.parts)
            try:
                target.resolve(strict=False).relative_to(temporary.resolve())
            except ValueError as exc:
                raise InvalidPathError("Proposal path escapes the worktree") from exc
            current = temporary
            for part in relative.parts[:-1]:
                current /= part
                if current.is_symlink():
                    raise InvalidPathError("Proposal path traverses a symlink")
            if target.exists():
                raise RepositoryError("Proposal path already exists; replacements are not supported")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content.rstrip("\n") + "\n", encoding="utf-8")
            self._git(temporary, "add", "--", relative.as_posix())
            self._git(temporary, "commit", "-m", title)
            commit = self._git(temporary, "rev-parse", "HEAD").stdout.strip()
            self._git(temporary, "push", self.remote, f"HEAD:refs/heads/{branch}")
            body = f"{rationale.strip()}\n\nBase commit: `{base_commit}`"
            if source_run_id:
                body += f"\nSource run: `{source_run_id}`"
            body += "\n\nCreated by memory-mcp; merge remains a human review decision."
            try:
                url = self.provider.open_review(
                    temporary,
                    base=self.base_branch,
                    head=branch,
                    title=title,
                    body=body,
                )
            except MemoryError as exc:
                raise RepositoryError(
                    "Proposal branch was pushed, but review creation failed. "
                    f"Remote branch: {branch}; commit: {commit}; "
                    f"base: {base_commit}; path: {relative.as_posix()}. "
                    f"The reviewed {self.base_branch} branch was not modified. "
                    "An administrator must open a review for this branch or "
                    f"delete it manually. Provider error: {exc}"
                ) from exc
            return {
                "provider": self.provider.name,
                "url": url,
                "branch": branch,
                "commit": commit,
                "base_commit": base_commit,
                "path": relative.as_posix(),
            }
        finally:
            if added:
                self._git(self.root, "worktree", "remove", "--force", str(temporary), check=False)
            shutil.rmtree(temporary, ignore_errors=True)
