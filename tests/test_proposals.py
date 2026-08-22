from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from memory_mcp.errors import InvalidPathError, MemoryError, RepositoryError
from memory_mcp.proposals import ProposalService
from conftest import git


class FakeProvider:
    name = "test-review"

    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def open_review(
        self, worktree: Path, *, base: str, head: str, title: str, body: str
    ) -> str:
        assert worktree.is_dir()
        self.calls.append(
            {"base": base, "head": head, "title": title, "body": body}
        )
        return "https://example.invalid/reviews/1"


class FailingProvider:
    name = "test-review"

    def open_review(
        self, worktree: Path, *, base: str, head: str, title: str, body: str
    ) -> str:
        raise RepositoryError("synthetic provider failure")


@pytest.fixture
def proposal_repo(repo: Path, tmp_path: Path) -> tuple[Path, Path]:
    remote = tmp_path.parent / f"{tmp_path.name}-remote.git"
    subprocess.run(
        ["git", "init", "--bare", "-q", str(remote)],
        check=True,
        text=True,
        capture_output=True,
    )
    git(repo, "branch", "-M", "main")
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-u", "origin", "main")
    return repo, remote


def test_proposal_uses_isolated_branch_and_leaves_checkout_unchanged(
    proposal_repo: tuple[Path, Path],
) -> None:
    repo, remote = proposal_repo
    provider = FakeProvider()
    service = ProposalService(repo, provider)
    original_head = git(repo, "rev-parse", "HEAD").stdout.strip()

    result = service.propose_memory(
        path="incidents/power-restoration.md",
        content="# Power restoration\n\nObserved at 02:30.",
        title="Document power restoration",
        rationale="Records reviewed operational context.",
        source_run_id="monitor-123",
    )

    assert result["provider"] == "test-review"
    assert result["url"] == "https://example.invalid/reviews/1"
    assert result["base_commit"] == original_head
    assert git(repo, "branch", "--show-current").stdout.strip() == "main"
    assert git(repo, "rev-parse", "HEAD").stdout.strip() == original_head
    assert git(repo, "status", "--porcelain").stdout == ""
    content = git(
        remote,
        "show",
        f"refs/heads/{result['branch']}:incidents/power-restoration.md",
    ).stdout
    assert content == "# Power restoration\n\nObserved at 02:30.\n"
    assert provider.calls == [
        {
            "base": "main",
            "head": result["branch"],
            "title": "Document power restoration",
            "body": (
                "Records reviewed operational context.\n\n"
                f"Base commit: `{original_head}`\n"
                "Source run: `monitor-123`\n\n"
                "Created by memory-mcp; merge remains a human review decision."
            ),
        }
    ]


def test_review_failure_reports_pushed_branch_for_admin_cleanup(
    proposal_repo: tuple[Path, Path],
) -> None:
    repo, remote = proposal_repo
    original_head = git(repo, "rev-parse", "HEAD").stdout.strip()

    with pytest.raises(RepositoryError) as raised:
        ProposalService(repo, FailingProvider()).propose_memory(
            path="incidents/provider-failure.md",
            content="# Provider failure",
            title="Record provider failure",
            rationale="Exercise post-push failure reporting.",
        )

    message = str(raised.value)
    assert "Proposal branch was pushed" in message
    assert "Remote branch: memory-proposal/" in message
    assert "commit:" in message
    assert f"base: {original_head}" in message
    assert "path: incidents/provider-failure.md" in message
    assert "main branch was not modified" in message
    assert "open a review for this branch or delete it manually" in message
    assert "synthetic provider failure" in message
    branch = message.split("Remote branch: ", 1)[1].split(";", 1)[0]
    assert git(remote, "show", f"refs/heads/{branch}:incidents/provider-failure.md").stdout == (
        "# Provider failure\n"
    )
    assert git(repo, "rev-parse", "HEAD").stdout.strip() == original_head
    assert git(repo, "status", "--porcelain").stdout == ""


@pytest.mark.parametrize(
    "path",
    ["../escape.md", "/absolute.md", ".github/workflows/change.md", "note.txt"],
)
def test_proposal_rejects_unsafe_or_non_markdown_paths(repo: Path, path: str) -> None:
    with pytest.raises(InvalidPathError):
        ProposalService(repo, FakeProvider()).propose_memory(
            path=path, content="safe", title="Safe", rationale="Safe"
        )


def test_proposal_rejects_existing_path(proposal_repo: tuple[Path, Path]) -> None:
    repo, _ = proposal_repo
    with pytest.raises(RepositoryError, match="already exists"):
        ProposalService(repo, FakeProvider()).propose_memory(
            path="notes/hello world.md",
            content="replacement",
            title="Replace memory",
            rationale="Should not overwrite reviewed content.",
        )


def test_proposal_refuses_dirty_checkout_before_remote_changes(
    proposal_repo: tuple[Path, Path],
) -> None:
    repo, remote = proposal_repo
    (repo / "dirty.md").write_text("local work\n", encoding="utf-8")
    provider = FakeProvider()
    with pytest.raises(RepositoryError, match="clean working tree"):
        ProposalService(repo, provider).propose_memory(
            path="notes/new.md", content="safe", title="Safe", rationale="Safe"
        )
    assert provider.calls == []
    assert git(remote, "for-each-ref", "--format=%(refname)", "refs/heads").stdout == (
        "refs/heads/main\n"
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("content", "password=supersecretvalue"),
        ("rationale", "Authorization: Bearer concealed"),
    ],
)
def test_proposal_scans_all_outbound_text_for_credentials(
    repo: Path, field: str, value: str
) -> None:
    arguments = {
        "path": "notes/new.md",
        "content": "safe",
        "title": "Safe",
        "rationale": "Safe",
    }
    arguments[field] = value
    with pytest.raises(MemoryError, match="credential-shaped"):
        ProposalService(repo, FakeProvider()).propose_memory(**arguments)


def test_proposal_bounds_source_identifier(repo: Path) -> None:
    with pytest.raises(MemoryError, match="Source run ID"):
        ProposalService(repo, FakeProvider()).propose_memory(
            path="notes/new.md",
            content="safe",
            title="Safe",
            rationale="Safe",
            source_run_id="line one\nline two",
        )


def test_refresh_fast_forwards_reviewed_main(proposal_repo: tuple[Path, Path]) -> None:
    repo, remote = proposal_repo
    other = repo.parent / "reviewer"
    subprocess.run(
        ["git", "clone", "-q", str(remote), str(other)],
        check=True,
        text=True,
        capture_output=True,
    )
    git(other, "config", "user.name", "Reviewer")
    git(other, "config", "user.email", "reviewer@example.invalid")
    (other / "reviewed.md").write_text("reviewed\n", encoding="utf-8")
    git(other, "add", "reviewed.md")
    git(other, "commit", "-qm", "reviewed memory")
    git(other, "push", "origin", "main")

    result = ProposalService(repo, FakeProvider()).refresh()

    assert result["changed"] is True
    assert result["before"] != result["after"]
    assert (repo / "reviewed.md").read_text(encoding="utf-8") == "reviewed\n"


def test_refresh_refuses_dirty_or_wrong_branch(proposal_repo: tuple[Path, Path]) -> None:
    repo, _ = proposal_repo
    service = ProposalService(repo, FakeProvider())
    (repo / "dirty.md").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(RepositoryError, match="clean working tree"):
        service.refresh()
    (repo / "dirty.md").unlink()
    git(repo, "switch", "-c", "other")
    with pytest.raises(RepositoryError, match="must be on main"):
        service.refresh()


@pytest.mark.parametrize("value", ["-origin", "../main", "bad ref", "/"])
def test_invalid_git_configuration_is_rejected(repo: Path, value: str) -> None:
    with pytest.raises(MemoryError, match="Invalid proposal"):
        ProposalService(repo, FakeProvider(), remote=value)
