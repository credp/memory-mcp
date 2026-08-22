# memory-mcp

`memory-mcp` is a small, local [Model Context Protocol](https://modelcontextprotocol.io/) server for a user-owned Git repository of durable memory. It gives agents reliable mechanisms to list, read, search, inspect history and diffs, capture unstructured text, or submit bounded changes for review.

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

The Python core and each running server instance are bound to exactly one configured repository root. It validates repository-relative paths and provides dependency-light filesystem and Git operations. A thin adapter exposes those operations as MCP tools over stdio. Read-only and capture modes make no network requests and send no telemetry. Pull-request mode deliberately uses Git and a configured forge provider to refresh reviewed memory and publish proposals.

Installations that use more than one memory repository should configure a
separate MCP server instance for each repository. The MCP client gives each
instance a distinct name and starts it with that repository's own
`MEMORY_MCP_REPOSITORY` and, where appropriate, `MEMORY_MCP_MODE`. This keeps
repository selection and permissions at the MCP configuration boundary rather
than adding routing or cross-repository operations to `memory-mcp`.

The memory repository may use any layout. Names such as `projects/`, `principles/`, or `inbox/` carry no protocol meaning. V1 understands only a repository, relative paths, text files, and Git changes.

Python 3.11+ was chosen for its mature standard-library filesystem, subprocess, atomic-file, and testing support. The official MCP SDK is the sole runtime dependency. Text search is implemented locally in Python, so `ripgrep` is not required. Git must be installed.

## Install and configure

Using [`uv`](https://docs.astral.sh/uv/):

```sh
git clone https://github.com/credp/memory-mcp.git
cd memory-mcp
uv sync
```

Create or choose a separate Git repository for memory:

```sh
mkdir -p "$HOME/Projects/memory"
git -C "$HOME/Projects/memory" init
```

Set `MEMORY_MCP_REPOSITORY` in the process environment to that repository's root. Do not put a private absolute path in a committed configuration file.

The server defaults to **read-only mode**. In this mode it does not register or
advertise any tool capable of changing the memory repository. To deliberately
enable new-file capture, set `MEMORY_MCP_MODE=read-write`. To use reviewed
contributions instead, set `MEMORY_MCP_MODE=pull-request`. Any other value is
rejected, so a typo cannot accidentally enable writes.

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

### Updating the memory repository

General memory updates may happen through ordinary filesystem and Git tools, or
through the optional pull-request workflow. In either case, the Git repository
remains the source of truth.

The only current MCP write mechanism is the optional `capture` tool, which is
available when a server instance is explicitly configured with
`MEMORY_MCP_MODE=read-write`. Capture only creates a new untracked Markdown file
and is not a general editing or repository-maintenance interface. In the default
read-only mode, all updates must happen outside the MCP server.

In `pull-request` mode, `refresh` fetches and fast-forwards a clean checkout of
the configured reviewed branch. `propose_memory` creates one new Markdown file
from that remote base in a disposable worktree, commits only that file, pushes
a new branch, and asks the configured provider to open a review. It never
approves or merges reviews, never rewrites history, and refuses a dirty primary
checkout or an existing destination path.

GitHub is the first provider. It uses the `gh` CLI and its existing
authentication, so install `gh` and authenticate the service identity before
starting the server. For unattended deployment, give that identity only the
repository permissions needed to read contents, push proposal branches, and
open pull requests. Supplying and rotating a GitHub App installation token is
an operator concern; do not put it in the memory repository or MCP arguments.
GitLab can be added as a separate provider without changing the proposal
service or MCP contract.

```json
{
  "MEMORY_MCP_MODE": "pull-request",
  "MEMORY_MCP_REPOSITORY": "/path/to/private/memory",
  "MEMORY_MCP_PROPOSAL_PROVIDER": "github",
  "MEMORY_MCP_PROPOSAL_REMOTE": "origin",
  "MEMORY_MCP_PROPOSAL_BASE_BRANCH": "main",
  "MEMORY_MCP_PROPOSAL_BRANCH_PREFIX": "memory-proposal"
}
```

### Protected local service

When Codex must not inherit the GitHub credential, install pull-request mode as
a persistent loopback service under a separate Unix identity. This installer is
Linux/systemd-specific. It requires an existing clean checkout on `main`, a
credential-free `https://github.com/...` origin, the `gh` CLI, and root access.

Create a fine-grained PAT restricted to the memory repository with repository
permissions `Contents: read and write` and `Pull requests: write`. Then run:

```sh
sudo "$(command -v memory-mcp-service)" install home-operations \
  --repository /srv/memory/home-operations \
  --port 8771 \
  --take-ownership
```

The ownership flag is deliberately mandatory because the installer recursively
transfers the checkout to the dedicated `memory-mcp-home-operations` service
account. The installer prompts for the PAT without echo; it never accepts the
token in command-line arguments. It stores the source credential at
`/etc/memory-mcp/home-operations/github_pat` with root-only permissions and
passes it to the service through systemd's credential mechanism.

The command prints the corresponding Codex registration command:

```sh
codex mcp add home-operations --url http://127.0.0.1:8771/mcp
```

Codex knows only the loopback MCP address. The PAT, writable checkout, GitHub
CLI and outbound provider access remain in the separate service process. Any
local process able to reach that loopback port can invoke the bounded MCP tools,
so use host firewall rules when local users require different tool access.

Review the generated unit without installing anything:

```sh
memory-mcp-service print-unit home-operations \
  --repository /srv/memory/home-operations \
  --port 8771
```

Rotate the PAT without putting it in shell history:

```sh
sudo "$(command -v memory-mcp-service)" rotate-token home-operations
```

Remove the service and credential while deliberately preserving the repository:

```sh
sudo "$(command -v memory-mcp-service)" uninstall home-operations
```

Uninstall leaves the dedicated service account and repository ownership intact
so it cannot orphan repository files under a deleted numeric UID. Reassign or
remove those explicitly after preserving any required Git work.

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

#### Tell Codex about persistent memory

The server advertises its purpose through the MCP `instructions` field, but a
small global Codex instruction makes the intended relationship explicit: this
repository is the user's persistent context across agents, chats, and projects,
not merely a tool to use when working on `memory-mcp` itself.

Add the following boilerplate to `$CODEX_HOME/AGENTS.md`. `CODEX_HOME` defaults
to `~/.codex`, so the usual location is `~/.codex/AGENTS.md`:

```md
## Persistent memory

A user-owned persistent memory is available through the `memory` MCP.

Use it as the primary place to read or store durable context relevant to the
user's request, including prior decisions, preferences, constraints, projects,
and historical reasoning.

Search memory when existing context could materially improve the task. Do not
assume every request requires memory.

Treat retrieved memories as supporting context, not unquestionable truth.
Prefer reviewed/current material over inbox, candidate, or historical material.

Store information only when it is likely to remain useful across future agents
or conversations. Do not store credentials, secrets, or sensitive information
unless the user explicitly requests it.
```

Codex reads this global file before project-level `AGENTS.md` files. If
`$CODEX_HOME/AGENTS.override.md` exists and is non-empty, Codex uses it instead
of the global `AGENTS.md`; put the boilerplate there as well, or remove the
override, if the memory guidance is not being loaded. Start a new Codex session
after changing the file because the instruction chain is assembled once per
run.

This is intentionally a relevance rule, not a requirement to load memory at
the start of every session. Codex should consult memory when it can improve the
user's task and leave it alone for self-contained requests.

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
- `capture(content, destination="")` is available only in explicit `read-write` mode. It writes the content unchanged (apart from ensuring a final newline) to a new Markdown file. `destination` is a configurable, existing relative directory; the neutral default is the repository root. Creation uses an exclusive filename and does not stage or commit anything.
- `refresh()` is available only in `pull-request` mode. It requires a clean checkout on the configured base branch, fetches that branch, and applies only a fast-forward update.
- `propose_memory(path, content, title, rationale, source_run_id="")` is available only in `pull-request` mode. It accepts a new repository-relative Markdown path, scans all outbound text for common credential shapes, creates an isolated contribution, and returns the review URL and Git provenance.

File reads are limited to 2 MiB, search skips files over 2 MiB, history is limited to 100 commits, and search is limited to 1,000 matches. These conservative v1 bounds keep MCP responses manageable.

## Security and privacy

Each `MemoryRepository` instance is a security boundary. All external paths are relative to its exact Git root. Absolute paths, traversal with `..`, and symlinks resolving outside the root are rejected. Recursive operations do not follow symlinks, and returned data does not reveal the configured absolute path.

Each server instance exposes one repository and defaults to read-only access.
Operators can explicitly opt into read-write capture with
`MEMORY_MCP_MODE=read-write`. Multiple repositories are exposed through
separately named MCP server instances, so each repository retains an independent
security and permission boundary. A server instance never routes to another
repository or performs cross-repository operations.

Repository content stays local in read-only and capture modes. Pull-request mode
sends the proposed content, title, rationale, branch, and commit to the Git
remote and review provider. There is no external indexing, analytics, or
telemetry. MCP clients, agents, Git hosting, and the narrowly scoped service
identity are therefore part of that mode's trust boundary.

Capture creates an obvious untracked file with mode `0600`. Pull-request mode
never resets or discards local work, rewrites history, approves reviews, or
merges them. Its contribution branches are intentionally visible on the remote;
if review creation fails after a successful push, the branch remains available
for diagnosis or manual review rather than being deleted implicitly.

## Development

```sh
uv sync --extra dev
uv run pytest
```

Tests create isolated temporary Git repositories and cover listing, reading, literal search, history, diff, capture, dirty trees, spaces, Unicode, traversal, escaping symlinks, missing/non-Git/empty repositories, malformed and oversized files, capture filename collisions, and Git failures.

To prepare a patch release from a clean working tree:

```sh
make release
```

`make release` defaults to a patch increment (for example, `0.0.2` to `0.0.3`);
`make release BUMP=patch` is the explicit equivalent. Use
`make release BUMP=minor` or `make release BUMP=major` when those larger version
increments are intended. The command runs the tests, updates `pyproject.toml`
and `uv.lock`, creates a release commit, and adds the matching annotated Git
tag locally. It prints the separate `git push` command needed to publish the
release.

## Roadmap

**Phase 1 (implemented):** read-only-by-default list, read, textual search,
history, and diff; optional explicit read-write capture.

**Phase 2 (implemented for new memories):** optional GitHub pull-request
contributions created in isolated worktrees, with a provider boundary for other
forges. Broader edit, rename, and deletion proposals remain future work.

**Phase 3:** improve support and documentation for multi-memory installations
by running one separately named MCP server instance per repository. Each
instance remains bound to one repository and has its own access mode; repository
routing, discovery, and cross-repository operations remain outside the server.

Possible later experiments include semantic search, local embeddings, related-memory discovery, structured frontmatter, and agent-assisted consolidation. They must remain optional layers; the core will never require them.

The governing design test is simple: if `memory-mcp` disappeared tomorrow, the user would still own a clean, understandable, useful Git repository containing all memories and history.
