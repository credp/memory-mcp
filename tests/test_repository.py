from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from memory_mcp.errors import InvalidPathError, MemoryError, RepositoryError
from memory_mcp.repository import MAX_READ_BYTES, MemoryRepository
from memory_mcp.server import SERVER_INSTRUCTIONS, mcp
from conftest import git


def test_server_exposes_memory_usage_guidance() -> None:
    assert mcp.instructions == SERVER_INSTRUCTIONS
    assert "Search memory before assuming" in mcp.instructions
    assert "supporting context, not unquestionable truth" in mcp.instructions
    assert "prefer reviewed/current material" in mcp.instructions


def test_list_normal_recursive_and_hides_git(memory: MemoryRepository) -> None:
    shallow = memory.list_memories()
    assert [item["path"] for item in shallow["entries"]] == ["inbox", "notes"]
    recursive = memory.list_memories(recursive=True)
    assert "notes/hello world.md" in [item["path"] for item in recursive["entries"]]
    assert all(".git" not in item["path"].split("/") for item in recursive["entries"])


def test_read_file_with_spaces_and_unicode(memory: MemoryRepository) -> None:
    result = memory.read_memory("notes/hello world.md")
    assert result["content"].startswith("# Héllo")
    assert result["path"] == "notes/hello world.md"
    assert result["size"] > 0
    assert "+00:00" in result["modified_at"]


def test_literal_text_search(memory: MemoryRepository) -> None:
    insensitive = memory.search_memories("DURABLE")
    assert insensitive["matches"][0]["line_number"] == 2
    assert insensitive["matches"][0]["path"] == "notes/hello world.md"
    assert memory.search_memories("DURABLE", case_sensitive=True)["matches"] == []


def test_history_for_path(memory: MemoryRepository) -> None:
    result = memory.history("notes/hello world.md")
    assert len(result["commits"]) == 1
    assert result["commits"][0]["message"] == "initial memory"
    assert result["commits"][0]["author"] == "Test User"
    assert len(result["commits"][0]["commit"]) == 40


def test_diff_reports_changes_without_modifying_dirty_tree(memory: MemoryRepository, repo: Path) -> None:
    note = repo / "notes" / "hello world.md"
    note.write_text("changed\n", encoding="utf-8")
    (repo / "untracked.md").write_text("new\n", encoding="utf-8")
    before = git(repo, "status", "--porcelain").stdout
    result = memory.diff()
    after = git(repo, "status", "--porcelain").stdout
    assert "-# Héllo" in result["patch"]
    assert result["untracked"] == ["untracked.md"]
    assert after == before


def test_capture_is_verbatim_auditable_and_untracked(memory: MemoryRepository, repo: Path) -> None:
    result = memory.capture("raw idea 🧠", "inbox")
    target = repo / result["path"]
    assert target.read_text(encoding="utf-8") == "raw idea 🧠\n"
    assert target.stat().st_mode & 0o777 == 0o600
    assert result["path"].startswith("inbox/") and result["path"].endswith(".md")
    assert result["path"] in memory.diff()["untracked"]


def test_simultaneous_style_captures_get_unique_names(memory: MemoryRepository) -> None:
    paths = {memory.capture("same", "inbox")["path"] for _ in range(20)}
    assert len(paths) == 20


@pytest.mark.parametrize("bad", ["../secret", "notes/../../secret", "/etc/passwd"])
def test_path_traversal_is_rejected(memory: MemoryRepository, bad: str) -> None:
    with pytest.raises(InvalidPathError):
        memory.read_memory(bad)


def test_symlink_escaping_root_cannot_be_read_or_searched(memory: MemoryRepository, repo: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    outside = tmp_path_factory.mktemp("outside") / "secret.md"
    outside.write_text("private secret", encoding="utf-8")
    (repo / "escape.md").symlink_to(outside)
    with pytest.raises(InvalidPathError):
        memory.read_memory("escape.md")
    assert memory.search_memories("private secret")["matches"] == []
    listed = {item["path"]: item["type"] for item in memory.list_memories()["entries"]}
    assert listed["escape.md"] == "symlink"


def test_missing_and_non_git_repositories_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(RepositoryError):
        MemoryRepository(tmp_path / "missing")
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(RepositoryError):
        MemoryRepository(plain)


def test_nested_git_directory_is_not_accepted(repo: Path) -> None:
    with pytest.raises(RepositoryError):
        MemoryRepository(repo / "notes")


def test_empty_unborn_repository(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q")
    memory = MemoryRepository(tmp_path)
    assert memory.history()["commits"] == []
    assert memory.diff()["base"] is None
    assert memory.list_memories()["entries"] == []


def test_binary_and_malformed_utf8_are_not_exposed(memory: MemoryRepository, repo: Path) -> None:
    malformed = repo / "bad.bin"
    malformed.write_bytes(b"\xff\x00secret")
    with pytest.raises(MemoryError, match="UTF-8"):
        memory.read_memory("bad.bin")
    result = memory.search_memories("secret")
    assert result["matches"] == []
    assert result["skipped_files"] == 1


def test_oversized_read_is_rejected(memory: MemoryRepository, repo: Path) -> None:
    (repo / "large.md").write_bytes(b"x" * (MAX_READ_BYTES + 1))
    with pytest.raises(MemoryError, match="read limit"):
        memory.read_memory("large.md")


def test_git_failure_is_safely_reported(memory: MemoryRepository, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 2, "", "synthetic failure")

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(RepositoryError, match="synthetic failure"):
        memory.history()


def test_capture_does_not_overwrite_or_stage_existing_changes(memory: MemoryRepository, repo: Path) -> None:
    existing = repo / "notes" / "hello world.md"
    existing.write_text("user edit\n", encoding="utf-8")
    before = existing.read_bytes()
    memory.capture("separate thought", "inbox")
    assert existing.read_bytes() == before
    assert git(repo, "diff", "--cached", "--name-only").stdout == ""


def test_invalid_inputs_are_bounded(memory: MemoryRepository) -> None:
    with pytest.raises(MemoryError):
        memory.search_memories("")
    with pytest.raises(MemoryError):
        memory.search_memories("x", limit=1001)
    with pytest.raises(MemoryError):
        memory.history(limit=0)
    with pytest.raises(MemoryError):
        memory.capture("  ", "inbox")

