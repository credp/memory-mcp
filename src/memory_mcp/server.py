from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .errors import MemoryError
from .proposals import ProposalService
from .providers import GitHubCliProvider
from .repository import MemoryRepository

READ_ONLY_MODE = "read-only"
READ_WRITE_MODE = "read-write"
PULL_REQUEST_MODE = "pull-request"
VALID_MODES = {READ_ONLY_MODE, READ_WRITE_MODE, PULL_REQUEST_MODE}


def configured_mode() -> str:
    """Return the deployment mode, failing closed on invalid configuration."""
    mode = os.environ.get("MEMORY_MCP_MODE", READ_ONLY_MODE).strip().lower()
    if mode not in VALID_MODES:
        choices = ", ".join(sorted(VALID_MODES))
        raise MemoryError(f"MEMORY_MCP_MODE must be one of: {choices}")
    return mode


MODE = configured_mode()

SERVER_INSTRUCTIONS = """This server is the user's persistent memory across agents and conversations.

Use it as the primary place to read or store durable context relevant to the
user's request, including prior decisions, preferences, constraints, projects,
historical reasoning, and previously explored ideas.

Search memory when existing context could materially improve the task, and
before assuming that a design decision is new or unexplored. Not every request
requires memory.

Treat memory as supporting context, not unquestionable truth.

Where the repository distinguishes reviewed/current material from candidate
material, prefer reviewed/current material unless the task requires otherwise.

Store information only when it is likely to remain useful across future agents
or conversations. Do not store credentials, secrets, or sensitive information
unless the user explicitly requests it."""

if MODE == READ_ONLY_MODE:
    SERVER_INSTRUCTIONS += """

This deployment is read-only. It provides no tool that creates or modifies
memories."""
elif MODE == PULL_REQUEST_MODE:
    SERVER_INSTRUCTIONS += """

This deployment uses reviewable Git contributions. Refresh reads only a clean
checkout of the reviewed base branch and fast-forwards it. propose_memory may
publish a new Markdown-only branch and open a review request, but it never
approves or merges one. Treat the returned review URL as pending until a human
reviews and merges it."""

mcp = FastMCP(
    "memory-mcp",
    instructions=SERVER_INSTRUCTIONS,
)


@lru_cache(maxsize=1)
def repository() -> MemoryRepository:
    path = os.environ.get("MEMORY_MCP_REPOSITORY")
    if not path:
        raise MemoryError("MEMORY_MCP_REPOSITORY is not configured")
    return MemoryRepository(path)


@lru_cache(maxsize=1)
def proposals() -> ProposalService:
    path = os.environ.get("MEMORY_MCP_REPOSITORY")
    if not path:
        raise MemoryError("MEMORY_MCP_REPOSITORY is not configured")
    provider = os.environ.get("MEMORY_MCP_PROPOSAL_PROVIDER", "github")
    if provider != "github":
        raise MemoryError("MEMORY_MCP_PROPOSAL_PROVIDER must be github")
    return ProposalService(
        repository().root,
        GitHubCliProvider(),
        remote=os.environ.get("MEMORY_MCP_PROPOSAL_REMOTE", "origin"),
        base_branch=os.environ.get("MEMORY_MCP_PROPOSAL_BASE_BRANCH", "main"),
        branch_prefix=os.environ.get("MEMORY_MCP_PROPOSAL_BRANCH_PREFIX", "memory-proposal"),
    )


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


def capture(content: str, destination: str = "") -> dict[str, Any]:
    """Atomically capture text verbatim in a new Markdown file; do not stage or commit it."""
    return repository().capture(content, destination)


if MODE == READ_WRITE_MODE:
    mcp.tool()(capture)


def refresh() -> dict[str, Any]:
    """Fetch and fast-forward the clean memory checkout to reviewed main."""
    return proposals().refresh()


def propose_memory(
    path: str,
    content: str,
    title: str,
    rationale: str,
    source_run_id: str = "",
) -> dict[str, Any]:
    """Create a Markdown-only contribution branch and open a review request."""
    return proposals().propose_memory(
        path=path, content=content, title=title, rationale=rationale,
        source_run_id=source_run_id,
    )


if MODE == PULL_REQUEST_MODE:
    mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=True,
        )
    )(refresh)
    mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=True,
        )
    )(propose_memory)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
