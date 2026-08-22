from __future__ import annotations

import os
from pathlib import Path


def main() -> None:
    host = os.environ.get("MEMORY_MCP_HOST", "127.0.0.1")
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise RuntimeError("Protected memory-mcp HTTP must bind to loopback")

    credentials_directory = os.environ.get("CREDENTIALS_DIRECTORY")
    if credentials_directory:
        credential = Path(credentials_directory) / "github_pat"
        if credential.is_file():
            token = credential.read_text(encoding="utf-8").strip()
            if not token:
                raise RuntimeError("GitHub credential is empty")
            os.environ["GH_TOKEN"] = token

    # Import after credential and mode environment has been prepared because
    # server tool registration is deliberately configuration-dependent.
    from .server import mcp

    mcp.settings.host = host
    mcp.settings.port = int(os.environ.get("MEMORY_MCP_PORT", "8771"))
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
