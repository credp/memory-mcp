from __future__ import annotations

import os
from pathlib import Path

import pytest

from memory_mcp.errors import MemoryError
from memory_mcp.github_askpass import main as askpass_main
from memory_mcp.service_installer import (
    _atomic_secret,
    render_unit,
    service_user,
    unit_name,
    validate_name,
    validate_port,
    validate_repository,
)
from conftest import git


def test_names_map_to_bounded_service_identities() -> None:
    assert validate_name("home-operations") == "home-operations"
    assert service_user("home-operations") == "memory-mcp-home-operations"
    assert unit_name("home-operations") == "memory-mcp-home-operations.service"


@pytest.mark.parametrize(
    "name", ["", "Upper", "-leading", "under_score", "a" * 21, "space here"]
)
def test_invalid_instance_names_are_rejected(name: str) -> None:
    with pytest.raises(MemoryError, match="Instance name"):
        validate_name(name)


@pytest.mark.parametrize("port", [0, 1023, 65536])
def test_privileged_or_invalid_ports_are_rejected(port: int) -> None:
    with pytest.raises(MemoryError, match="Port"):
        validate_port(port)


def test_repository_requires_clean_main_and_credential_free_github_remote(
    repo: Path,
) -> None:
    git(repo, "branch", "-M", "main")
    git(repo, "remote", "add", "origin", "https://github.com/example/memory.git")
    assert validate_repository(repo) == repo.resolve()

    (repo / "dirty.md").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(MemoryError, match="clean working tree"):
        validate_repository(repo)
    (repo / "dirty.md").unlink()

    git(repo, "remote", "set-url", "origin", "https://token@github.com/example/memory.git")
    with pytest.raises(MemoryError, match="credential-free"):
        validate_repository(repo)


def test_rendered_unit_keeps_pat_out_of_configuration(tmp_path: Path) -> None:
    unit = render_unit(
        name="operations",
        repository=tmp_path / "memory",
        port=8871,
        python=Path("/opt/memory-mcp/bin/python"),
        askpass=Path("/opt/memory-mcp/bin/memory-mcp-github-askpass"),
        credential=Path("/etc/memory-mcp/operations/github_pat"),
    )
    assert "User=memory-mcp-operations" in unit
    assert "MEMORY_MCP_MODE=pull-request" in unit
    assert "MEMORY_MCP_HOST=127.0.0.1" in unit
    assert "MEMORY_MCP_PORT=8871" in unit
    assert "LoadCredential=github_pat:/etc/memory-mcp/operations/github_pat" in unit
    assert "GH_TOKEN" not in unit
    assert "github_pat=" not in unit
    assert f"ReadWritePaths={tmp_path / 'memory'}" in unit
    assert "ProtectSystem=strict" in unit
    assert "BindReadOnlyPaths=/opt/memory-mcp" in unit


def test_secret_write_is_atomic_and_root_only(tmp_path: Path) -> None:
    target = tmp_path / "instance" / "github_pat"
    _atomic_secret(target, "github_pat_value")
    assert target.read_text(encoding="utf-8") == "github_pat_value\n"
    assert target.stat().st_mode & 0o777 == 0o600
    assert target.parent.stat().st_mode & 0o777 == 0o700


def test_askpass_reads_systemd_credential_only_for_password(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "github_pat").write_text("protected-token\n", encoding="utf-8")
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path))
    monkeypatch.setattr("sys.argv", ["memory-mcp-github-askpass", "Username for GitHub"])
    askpass_main()
    assert capsys.readouterr().out == "x-access-token\n"

    monkeypatch.setattr("sys.argv", ["memory-mcp-github-askpass", "Password for GitHub"])
    askpass_main()
    assert capsys.readouterr().out == "protected-token\n"


def test_askpass_fails_closed_without_credential_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    monkeypatch.setattr("sys.argv", ["memory-mcp-github-askpass", "Password"])
    with pytest.raises(SystemExit, match="CREDENTIALS_DIRECTORY"):
        askpass_main()
