# memory-mcp

`memory-mcp` is a small, local [Model Context Protocol](https://modelcontextprotocol.io/) server for a user-owned Git repository of durable memory. It gives agents reliable mechanisms to list, read, search, inspect history and diffs, and capture unstructured text.

> **The repository is the product's durable state. `memory-mcp` is merely an interface to it.**

It is deliberately not a database, ontology, knowledge graph, hosted service, agent, or automatic consolidation system. Markdown remains readable without this program. Git provides history, provenance, rollback, and the basis for future transactions. The agent—not the server—decides what a note means and how it should be organised: **mechanism below, intelligence above**.

```text
┌──────────────┐
│  AI agent    │
└──────┬───────┘
       │ MCP
┌──────▼───────┐
│  memory-mcp  │
│              │
│ mechanisms   │
└──────┬───────┘
       │ filesystem + Git
┌──────▼────────┐
│ memory repo   │
│               │
│ Markdown      │
│ Git history   │
└───────────────┘
```

## Architecture

The Python core is bound to exactly one configured repository root. It validates repository-relative paths and provides dependency-light filesystem and Git operations. A thin adapter exposes those operations as MCP tools over stdio. The server makes no network requests and sends no telemetry.

The memory repository may use any layout. Names such as `projects/`, `principles/`, or `inbox/` carry no protocol meaning. V1 understands only a repository, relative paths, text files, and Git changes.

Python 3.11+ was chosen for its mature standard-library filesystem, subprocess, atomic-file, and testing support. The official MCP SDK is the sole runtime dependency. Text search is implemented locally in Python, so `ripgrep` is not required. Git must be installed.

## Install and configure

Using [`uv`](https://docs.astral.sh/uv/):

```sh
git clone https://github.com/YOUR-ACCOUNT/memory-mcp.git
cd memory-mcp
uv sync
```

Create or choose a separate Git repository for memory:

```sh
mkdir -p "$HOME/Projects/memory"
git -C "$HOME/Projects/memory" init
```

Set `MEMORY_MCP_REPOSITORY` in the process environment to that repository's root. Do not put a private absolute path in a committed configuration file.

An MCP client configuration commonly looks like:

```json
{
  "mcpServers": {
    "memory": {
      "command": "uv",
      "args": ["--directory", "/path/to/memory-mcp", "run", "memory-mcp"],
      "env": {
        "MEMORY_MCP_REPOSITORY": "/path/to/private/memory"
      }
    }
  }
}
```

The exact outer configuration format varies by client. For a global install, `uv tool install .` provides the `memory-mcp` command.

### Codex

Codex CLI, the Codex IDE extension, and the ChatGPT desktop app share MCP
configuration on the same host. With this repository checked out locally, add
the server from a shell as follows, replacing the memory path if necessary:

```sh
cd /path/to/memory-mcp
uv sync
codex mcp add memory \
  --env MEMORY_MCP_REPOSITORY="$HOME/Projects/memory" \
  -- uv --directory "$PWD" run memory-mcp
```

Use an absolute path for the memory repository. The shell expands `$HOME` and
`$PWD` before Codex stores the configuration. Confirm the result with:

```sh
codex mcp list
```

Restart Codex after adding or changing the server. In the Codex terminal UI,
`/mcp` shows the active MCP servers and their tools.

To update a source-checkout installation when this upstream repository gains
new commits:

```sh
cd /path/to/memory-mcp
git pull --ff-only
uv sync
uv run pytest
```

Then restart Codex so it launches the updated server. The MCP configuration
does not need to be added again because it continues to point at the checkout.
`git pull --ff-only` deliberately stops instead of creating an implicit merge
if the local branch and upstream have diverged; review or preserve local work
before resolving that situation.

## Tools

- `list_memories(path="", recursive=false)` lists directory entries. `.git` internals are excluded.
- `read_memory(path)` reads a bounded, valid UTF-8 text file and returns relative-path metadata.
- `search_memories(query, path="", case_sensitive=false, limit=100)` performs deterministic literal line search. Oversized and malformed files are skipped.
- `history(path="", limit=20)` returns bounded Git history with commit, timestamp, author, and subject.
- `diff(path="")` returns tracked working-tree changes against `HEAD` and separately lists untracked files. In an unborn repository it reports the staged diff.
- `capture(content, destination="")` writes the content unchanged (apart from ensuring a final newline) to a new Markdown file. `destination` is a configurable, existing relative directory; the neutral default is the repository root. Creation uses an exclusive filename and does not stage or commit anything.

File reads are limited to 2 MiB, search skips files over 2 MiB, history is limited to 100 commits, and search is limited to 1,000 matches. These conservative v1 bounds keep MCP responses manageable.

## Security and privacy

Each `MemoryRepository` instance is a security boundary. All external paths are relative to its exact Git root. Absolute paths, traversal with `..`, and symlinks resolving outside the root are rejected. Recursive operations do not follow symlinks, and returned data does not reveal the configured absolute path.

V1 exposes one repository with read/write capture access. Its code is structured around a repository-bound object so future routing can give independent repositories read/write, read-only, or invisible status. Cross-repository search must remain impossible unless a later operation explicitly authorises named repositories.

Repository content stays local: there are no cloud calls, external indexing, analytics, or telemetry. The public server repository contains no user data or configured memory path. MCP clients and the agents using them are nevertheless part of the trust boundary: a client with access can read the configured repository and invoke capture.

Git operations are read-only in V1. The server never resets, discards changes, rewrites history, pushes, stages, or commits. Capture creates an obvious untracked file with mode `0600`. Dirty working trees are left intact.

## Proposed mutation model (Phase 2)

General-purpose editing needs reviewable Git contributions, not hidden writes or a second concurrency protocol:

1. `propose_change` accepts agent-constructed file operations or a patch and records the base commit the agent actually inspected. It validates paths and patch structure without changing the worktree, then returns the proposal and preview diff.
2. The user or agent reviews that diff.
3. `apply_change` applies that exact contribution using normal Git semantics. If the repository has diverged, the divergence or merge conflict is returned plainly for the agent or user to resolve; the MCP layer does not disguise it as a custom stale-version error.
4. A separate scoped-commit operation stages only the proposal's explicit paths, verifies the staged diff, and commits them. It refuses unrelated staged changes rather than absorbing them.

Proposals should be self-describing data, not server-generated semantic decisions. Deletions and renames need explicit representation. No operation should reset other work, rewrite history, or push.

Commits already identify their parents and Git already represents divergence, merging, and conflicts. Phase 2 must preserve that model: no repository lock service, shadow revision number, expected-`HEAD` gate, or per-file compare-and-swap layer. Agents should preferably work in an isolated branch or worktree when making contributions. A changing checkout can still race with filesystem writes, so apply must be narrowly scoped and must never reset or overwrite unrelated work. Concurrent captures use exclusive filenames only to prevent accidental overwrite; their ordering has no special meaning and Git remains responsible for reconciling them.

## Development

```sh
uv sync --extra dev
uv run pytest
```

Tests create isolated temporary Git repositories and cover listing, reading, literal search, history, diff, capture, dirty trees, spaces, Unicode, traversal, escaping symlinks, missing/non-Git/empty repositories, malformed and oversized files, capture filename collisions, and Git failures.

## Roadmap

**Phase 1 (implemented):** list, read, textual search, history, diff, capture.

**Phase 2:** `propose_change`, `apply_change`, scoped commits, base-commit provenance using ordinary Git history, and richer Markdown section addressing.

**Phase 3:** multiple repositories, per-repository permissions, repository discovery/configuration, and cross-repository operations only when explicitly authorised.

Possible later experiments include semantic search, local embeddings, related-memory discovery, structured frontmatter, and agent-assisted consolidation. They must remain optional layers; the core will never require them.

The governing design test is simple: if `memory-mcp` disappeared tomorrow, the user would still own a clean, understandable, useful Git repository containing all memories and history.
