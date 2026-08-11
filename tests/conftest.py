from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from memory_mcp import MemoryRepository


def git(path: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(path), *args], check=check, text=True, capture_output=True
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.name", "Test User")
    git(tmp_path, "config", "user.email", "test@example.invalid")
    (tmp_path / "inbox").mkdir()
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "hello world.md").write_text("# Héllo\nA durable thought.\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "initial memory")
    return tmp_path


@pytest.fixture
def memory(repo: Path) -> MemoryRepository:
    return MemoryRepository(repo)

