from __future__ import annotations

import argparse
import getpass
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .errors import MemoryError
from .repository import MemoryRepository


NAME = re.compile(r"^[a-z][a-z0-9-]{0,19}$")
SAFE_UNIT_PATH = re.compile(r"^/[A-Za-z0-9_./-]+$")
DEFAULT_CONFIG_ROOT = Path("/etc/memory-mcp")
DEFAULT_UNIT_ROOT = Path("/etc/systemd/system")


def service_user(name: str) -> str:
    return f"memory-mcp-{name}"


def unit_name(name: str) -> str:
    return f"memory-mcp-{name}.service"


def validate_name(name: str) -> str:
    if not NAME.fullmatch(name):
        raise MemoryError(
            "Instance name must start with a lowercase letter and contain at "
            "most 20 lowercase letters, digits, or hyphens"
        )
    return name


def validate_port(port: int) -> int:
    if not 1024 <= port <= 65535:
        raise MemoryError("Port must be between 1024 and 65535")
    return port


def validate_repository(value: str | Path) -> Path:
    repository = MemoryRepository(value)
    if repository._git("status", "--porcelain").stdout.strip():
        raise MemoryError("Repository must have a clean working tree")
    branch = repository._git("branch", "--show-current").stdout.strip()
    if branch != "main":
        raise MemoryError("Repository must be on main")
    remote = repository._git("remote", "get-url", "origin").stdout.strip()
    if not remote.startswith("https://github.com/") or "@" in remote.split("//", 1)[-1]:
        raise MemoryError(
            "origin must be a credential-free https://github.com/ repository URL"
        )
    root = repository.root
    if not SAFE_UNIT_PATH.fullmatch(str(root)):
        raise MemoryError(
            "Repository path contains characters unsupported by the systemd installer"
        )
    return root


def validate_unit_path(value: Path, label: str) -> Path:
    if not value.is_absolute() or not SAFE_UNIT_PATH.fullmatch(str(value)):
        raise MemoryError(f"{label} must be a simple absolute path")
    return value


def render_unit(
    *,
    name: str,
    repository: Path,
    port: int,
    python: Path,
    askpass: Path,
    credential: Path,
) -> str:
    validate_name(name)
    validate_port(port)
    for value, label in (
        (repository, "Repository"),
        (python, "Python executable"),
        (askpass, "Credential helper"),
        (credential, "Credential"),
    ):
        validate_unit_path(value, label)
    runtime = validate_unit_path(python.parent.parent, "Python runtime")
    user = service_user(name)
    return f"""[Unit]
Description=Protected memory-mcp instance {name}
After=network-online.target
Wants=network-online.target
ConditionPathIsDirectory={repository}

[Service]
Type=simple
User={user}
Group={user}
Environment=MEMORY_MCP_REPOSITORY={repository}
Environment=MEMORY_MCP_MODE=pull-request
Environment=MEMORY_MCP_HOST=127.0.0.1
Environment=MEMORY_MCP_PORT={port}
Environment=MEMORY_MCP_PROPOSAL_PROVIDER=github
Environment=MEMORY_MCP_PROPOSAL_REMOTE=origin
Environment=MEMORY_MCP_PROPOSAL_BASE_BRANCH=main
Environment=MEMORY_MCP_PROPOSAL_BRANCH_PREFIX=memory-proposal
Environment=GIT_ASKPASS={askpass}
Environment=GIT_TERMINAL_PROMPT=0
Environment="GIT_AUTHOR_NAME=memory-mcp proposal agent"
Environment=GIT_AUTHOR_EMAIL=memory-mcp@localhost
Environment="GIT_COMMITTER_NAME=memory-mcp proposal agent"
Environment=GIT_COMMITTER_EMAIL=memory-mcp@localhost
LoadCredential=github_pat:{credential}
ExecStart={python} -m memory_mcp.http_server
Restart=on-failure
RestartSec=5s
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
BindReadOnlyPaths={runtime}
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
ReadWritePaths={repository}

[Install]
WantedBy=multi-user.target
"""


def _run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, text=True, capture_output=True)


def _atomic_secret(path: Path, token: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(token + "\n")
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _read_token() -> str:
    token = getpass.getpass("GitHub fine-grained PAT: ").strip()
    if not token or len(token) > 1024 or any(character.isspace() for character in token):
        raise MemoryError(
            "GitHub token must be non-empty, contain no whitespace, and be at most 1024 characters"
        )
    return token


def _require_root() -> None:
    if os.geteuid() != 0:
        raise MemoryError("This operation must run as root")


def install(args: argparse.Namespace) -> None:
    _require_root()
    name = validate_name(args.name)
    port = validate_port(args.port)
    repository = validate_repository(args.repository)
    if not args.take_ownership:
        raise MemoryError(
            "Refusing to change repository ownership without --take-ownership"
        )
    if not shutil.which("gh"):
        raise MemoryError("The gh CLI must be installed before protected mode")
    unit_path = DEFAULT_UNIT_ROOT / unit_name(name)
    if unit_path.exists():
        raise MemoryError(f"Instance is already installed: {name}")
    python = Path(sys.executable).absolute()
    askpass = python.parent / "memory-mcp-github-askpass"
    if not askpass.is_file():
        raise MemoryError(f"Packaged credential helper is missing: {askpass}")
    token = _read_token()
    user = service_user(name)
    if _run("id", "-u", user, check=False).returncode != 0:
        _run(
            "useradd",
            "--system",
            "--home-dir",
            "/nonexistent",
            "--shell",
            "/usr/sbin/nologin",
            user,
        )
    _run("chown", "-R", f"{user}:{user}", str(repository))

    credential = DEFAULT_CONFIG_ROOT / name / "github_pat"
    _atomic_secret(credential, token)
    unit = render_unit(
        name=name,
        repository=repository,
        port=port,
        python=python,
        askpass=askpass,
        credential=credential,
    )
    unit_path.write_text(unit, encoding="utf-8")
    os.chmod(unit_path, 0o644)
    _run("systemctl", "daemon-reload")
    _run("systemctl", "enable", "--now", unit_name(name))
    print(f"Installed {unit_name(name)} on http://127.0.0.1:{port}/mcp")
    print(f"codex mcp add {name} --url http://127.0.0.1:{port}/mcp")


def rotate(args: argparse.Namespace) -> None:
    _require_root()
    name = validate_name(args.name)
    unit = DEFAULT_UNIT_ROOT / unit_name(name)
    if not unit.is_file():
        raise MemoryError(f"Instance is not installed: {name}")
    _atomic_secret(DEFAULT_CONFIG_ROOT / name / "github_pat", _read_token())
    _run("systemctl", "restart", unit_name(name))
    print(f"Rotated the credential for {unit_name(name)}")


def uninstall(args: argparse.Namespace) -> None:
    _require_root()
    name = validate_name(args.name)
    unit = DEFAULT_UNIT_ROOT / unit_name(name)
    _run("systemctl", "disable", "--now", unit_name(name), check=False)
    unit.unlink(missing_ok=True)
    credential = DEFAULT_CONFIG_ROOT / name / "github_pat"
    credential.unlink(missing_ok=True)
    try:
        credential.parent.rmdir()
    except OSError:
        pass
    _run("systemctl", "daemon-reload")
    print("Removed the service and credential; the memory repository was preserved")


def print_unit(args: argparse.Namespace) -> None:
    name = validate_name(args.name)
    port = validate_port(args.port)
    repository = Path(args.repository).expanduser().resolve()
    python = Path(sys.executable).absolute()
    print(
        render_unit(
            name=name,
            repository=repository,
            port=port,
            python=python,
            askpass=python.parent / "memory-mcp-github-askpass",
            credential=DEFAULT_CONFIG_ROOT / name / "github_pat",
        ),
        end="",
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="memory-mcp-service",
        description="Install a PAT-isolated memory-mcp loopback service",
    )
    commands = result.add_subparsers(dest="command", required=True)
    install_parser = commands.add_parser("install")
    install_parser.add_argument("name")
    install_parser.add_argument("--repository", required=True)
    install_parser.add_argument("--port", type=int, default=8771)
    install_parser.add_argument("--take-ownership", action="store_true")
    install_parser.set_defaults(handler=install)
    rotate_parser = commands.add_parser("rotate-token")
    rotate_parser.add_argument("name")
    rotate_parser.set_defaults(handler=rotate)
    uninstall_parser = commands.add_parser("uninstall")
    uninstall_parser.add_argument("name")
    uninstall_parser.set_defaults(handler=uninstall)
    print_parser = commands.add_parser("print-unit")
    print_parser.add_argument("name")
    print_parser.add_argument("--repository", required=True)
    print_parser.add_argument("--port", type=int, default=8771)
    print_parser.set_defaults(handler=print_unit)
    return result


def main() -> None:
    try:
        args = parser().parse_args()
        args.handler(args)
    except (MemoryError, OSError, subprocess.SubprocessError) as exc:
        raise SystemExit(f"memory-mcp-service: {exc}") from exc


if __name__ == "__main__":
    main()
