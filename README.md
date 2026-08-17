# recall

Give your AI agents a living memory.

`recall` keeps a simple, plain-text memory file per project and wires Hermes,
Claude Code, and Codex to read it at the start of every session. Save a fact
once, and every agent picks it up automatically. No more repeating yourself,
no more agents that forgot who you are.

## Install

```bash
uv tool install --from . recall
```

## Quick start

```bash
# Set up recall in the current project (creates .recall/memory.md
# and points AGENTS.md / CLAUDE.md at it)
recall init

# Remember a fact
recall save "I'm building recall, a cross-agent memory tool."

# See the whole memory
recall load
```

## How it works

- **One memory file per project**: `.recall/memory.md`, a plain dated list.
  Any agent can read it with zero tooling.
- **Wiring**: `recall init` adds a small pointer block to the files each
  agent already reads. Hermes and Codex read `AGENTS.md`; Claude Code reads
  `CLAUDE.md`. The pointer block is idempotent, so running `init` again never
  duplicates it and never clobbers what's already in the file.
- **Cross-agent by design**: adding support for another agent later is one
  line in the wiring map.

## Commands

| Command | What it does |
|---|---|
| `recall init [--agents hermes claude codex]` | Create the memory file and wire agents to read it |
| `recall save "<fact>"` | Append a dated entry to the memory file |
| `recall load` | Print the project's full memory |

## License

MIT
