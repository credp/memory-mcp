from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from mcp.server.fastmcp import FastMCP

from .errors import MemoryError
from .repository import MemoryRepository

mcp = FastMCP(
    "memory-mcp",
    instructions="Local filesystem and Git mechanisms for a user-owned memory repository.",
)


@lru_cache(maxsize=1)
def repository() -> MemoryRepository:
    path = os.environ.get("MEMORY_MCP_REPOSITORY")
    if not path:
        raise MemoryError("MEMORY_MCP_REPOSITORY is not configured")
    return MemoryRepository(path)


@mcp.tool()
def list_memories(path: str = "", recursive: bool = False) -> dict[str, Any]:
    """List files and directories below a repository-relative path."""
    return repository().list_memories(path, recursive)


@mcp.tool()
def read_memory(path: str) -> dict[str, Any]:
    """Read a UTF-8 text memory at a repository-relative path."""
    return repository().read_memory(path)


@mcp.tool()
def search_memories(query: str, path: str = "", case_sensitive: bool = False, limit: int = 100) -> dict[str, Any]:
    """Search UTF-8 memory files for literal text, returning matching lines."""
    return repository().search_memories(query, path, case_sensitive, limit)


@mcp.tool()
def history(path: str = "", limit: int = 20) -> dict[str, Any]:
    """Return bounded Git commit history for the repository or a relative path."""
    return repository().history(path, limit)


@mcp.tool()
def diff(path: str = "") -> dict[str, Any]:
    """Return tracked working-tree changes against HEAD and list untracked files."""
    return repository().diff(path)


@mcp.tool()
def capture(content: str, destination: str = "") -> dict[str, Any]:
    """Atomically capture text verbatim in a new Markdown file; do not stage or commit it."""
    return repository().capture(content, destination)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
