from __future__ import annotations

import os
import secrets
import subprocess
from datetime import datetime, timezone
from pathlib import Path, PurePath
from typing import Any

from .errors import InvalidPathError, MemoryError, RepositoryError

MAX_READ_BYTES = 2 * 1024 * 1024
MAX_SEARCH_FILE_BYTES = 2 * 1024 * 1024


class MemoryRepository:
    """Filesystem and Git mechanisms scoped to one repository boundary."""

    def __init__(self, root: str | Path):
        supplied = Path(root).expanduser()
        if not supplied.exists() or not supplied.is_dir():
            raise RepositoryError("Configured memory repository does not exist or is not a directory")
        self._root = supplied.resolve()
        result = self._git("rev-parse", "--is-inside-work-tree", check=False)
        if result.returncode != 0 or result.stdout.strip() != "true":
            raise RepositoryError("Configured memory repository is not a Git working tree")
        top = self._git("rev-parse", "--show-toplevel").stdout.strip()
        if Path(top).resolve() != self._root:
            raise RepositoryError("Configured path must be the root of its Git working tree")

    @property
    def root(self) -> Path:
        """Return the validated repository root for internal service composition."""
        return self._root

    def _resolve(self, relative: str = "", *, must_exist: bool = True) -> Path:
        raw = Path(relative or ".")
        if raw.is_absolute() or ".." in PurePath(relative).parts:
            raise InvalidPathError("Path must be relative and may not contain '..'")
        candidate = (self._root / raw).resolve(strict=False)
        try:
            candidate.relative_to(self._root)
        except ValueError as exc:
            raise InvalidPathError("Path escapes the configured repository") from exc
        if must_exist and not candidate.exists():
            raise InvalidPathError("Path does not exist")
        return candidate

    def _relative(self, path: Path) -> str:
        return path.relative_to(self._root).as_posix()

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(
                ["git", "-C", str(self._root), "--literal-pathspecs", *args],
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RepositoryError(f"Git command failed: {exc}") from exc
        if check and result.returncode != 0:
            message = result.stderr.strip() or "unknown Git error"
            raise RepositoryError(f"Git command failed: {message}")
        return result

    def head(self) -> str | None:
        result = self._git("rev-parse", "--verify", "HEAD", check=False)
        if result.returncode == 0:
            return result.stdout.strip()
        # A valid symbolic HEAD distinguishes an unborn repository from an
        # arbitrary Git failure, which must not be silently reported as empty.
        unborn = self._git("symbolic-ref", "-q", "HEAD", check=False)
        if unborn.returncode == 0 and unborn.stdout.strip():
            return None
        message = result.stderr.strip() or unborn.stderr.strip() or "could not resolve HEAD"
        raise RepositoryError(f"Git command failed: {message}")

    def list_memories(self, path: str = "", recursive: bool = False) -> dict[str, Any]:
        base = self._resolve(path)
        if not base.is_dir():
            raise InvalidPathError("Path is not a directory")
        iterator = base.rglob("*") if recursive else base.iterdir()
        entries: list[dict[str, Any]] = []
        for item in sorted(iterator, key=lambda value: value.as_posix()):
            relative = self._relative(item)
            if ".git" in item.relative_to(self._root).parts:
                continue
            if item.is_symlink():
                kind = "symlink"
            elif item.is_dir():
                kind = "directory"
            elif item.is_file():
                kind = "file"
            else:
                kind = "other"
            entry: dict[str, Any] = {"path": relative, "type": kind}
            if kind == "file":
                entry["size"] = item.stat().st_size
            entries.append(entry)
        return {"path": path, "recursive": recursive, "entries": entries}

    def read_memory(self, path: str) -> dict[str, Any]:
        target = self._resolve(path)
        if not target.is_file():
            raise InvalidPathError("Path is not a regular file")
        size = target.stat().st_size
        if size > MAX_READ_BYTES:
            raise MemoryError(f"File exceeds the {MAX_READ_BYTES}-byte read limit")
        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise MemoryError("File is not valid UTF-8 text") from exc
        stat = target.stat()
        return {
            "path": self._relative(target),
            "content": content,
            "size": size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        }

    def search_memories(
        self, query: str, path: str = "", case_sensitive: bool = False, limit: int = 100
    ) -> dict[str, Any]:
        if not query:
            raise MemoryError("Search query must not be empty")
        if not 1 <= limit <= 1000:
            raise MemoryError("Search limit must be between 1 and 1000")
        base = self._resolve(path)
        candidates = [base] if base.is_file() else base.rglob("*")
        needle = query if case_sensitive else query.casefold()
        matches: list[dict[str, Any]] = []
        skipped = 0
        for candidate in sorted(candidates, key=lambda value: value.as_posix()):
            if len(matches) >= limit:
                break
            if ".git" in candidate.relative_to(self._root).parts or candidate.is_symlink():
                continue
            if not candidate.is_file() or candidate.stat().st_size > MAX_SEARCH_FILE_BYTES:
                continue
            try:
                with candidate.open(encoding="utf-8") as stream:
                    for number, line in enumerate(stream, 1):
                        haystack = line if case_sensitive else line.casefold()
                        if needle in haystack:
                            matches.append({
                                "path": self._relative(candidate),
                                "line_number": number,
                                "line": line.rstrip("\r\n"),
                            })
                            if len(matches) >= limit:
                                break
            except (UnicodeDecodeError, OSError):
                skipped += 1
        return {"query": query, "matches": matches, "limit": limit, "truncated": len(matches) >= limit, "skipped_files": skipped}

    def history(self, path: str = "", limit: int = 20) -> dict[str, Any]:
        if not 1 <= limit <= 100:
            raise MemoryError("History limit must be between 1 and 100")
        if path:
            self._resolve(path, must_exist=False)
        if self.head() is None:
            return {"path": path or None, "commits": []}
        marker = "%x1f"
        args = ["log", f"--max-count={limit}", f"--format=%H{marker}%aI{marker}%an{marker}%s"]
        if path:
            args.extend(["--", path])
        result = self._git(*args)
        commits = []
        for line in result.stdout.splitlines():
            fields = line.split("\x1f", 3)
            if len(fields) == 4:
                commits.append(dict(zip(("commit", "timestamp", "author", "message"), fields)))
        return {"path": path or None, "commits": commits}

    def diff(self, path: str = "") -> dict[str, Any]:
        if path:
            self._resolve(path, must_exist=False)
        head = self.head()
        args = ["diff", "--no-ext-diff", "--no-color"]
        if head:
            args.append("HEAD")
        else:
            args.append("--cached")
        if path:
            args.extend(["--", path])
        patch = self._git(*args).stdout
        untracked_args = ["ls-files", "--others", "--exclude-standard"]
        if path:
            untracked_args.extend(["--", path])
        untracked = [line for line in self._git(*untracked_args).stdout.splitlines() if line]
        return {"base": head or None, "path": path or None, "patch": patch, "untracked": untracked}

    def capture(self, content: str, destination: str = "") -> dict[str, Any]:
        if not content.strip():
            raise MemoryError("Capture content must not be empty")
        directory = self._resolve(destination)
        if not directory.is_dir():
            raise InvalidPathError("Capture destination is not a directory")
        now = datetime.now(timezone.utc)
        body = content
        if not body.endswith("\n"):
            body += "\n"
        for _ in range(10):
            name = f"{now.strftime('%Y%m%dT%H%M%S.%fZ')}-{secrets.token_hex(4)}.md"
            target = directory / name
            try:
                descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                continue
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                    stream.write(body)
            except Exception:
                target.unlink(missing_ok=True)
                raise
            return {"path": self._relative(target), "size": len(body.encode("utf-8")), "created": True}
        raise MemoryError("Could not allocate a unique capture filename")
