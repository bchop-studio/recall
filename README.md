# recall

![recall](cover.png)

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

# See the whole live memory
recall load

# Find memories that may have gone stale
recall review

# Keep memory 1 and refresh its review date
recall keep 1

# Review again, then move memory 1 out of live context without deleting it
recall review
recall archive 1
```

## How it works

- **One memory file per project**: `.recall/memory.md`, a plain dated list.
  Any agent can read it with zero tooling.
- **Wiring**: `recall init` adds a small pointer block to the files each
  agent already reads. Hermes and Codex read `AGENTS.md`; Claude Code reads
  `CLAUDE.md`. The pointer block is idempotent, so running `init` again never
  duplicates it and never clobbers what's already in the file.
- **Memory hygiene**: `recall review` creates a numbered snapshot of memories
  that are 30 days old by default. `recall keep <number>` confirms one is still
  true and refreshes its date. `recall archive <number>` removes stale context
  from the live file and preserves it in `.recall/archive.md`. After either
  action, run `recall review` again before choosing another number.
- **Cross-agent by design**: adding support for another agent later is one
  line in the wiring map.

## Commands

| Command | What it does |
|---|---|
| `recall init [--agents hermes claude codex]` | Create the memory file and wire agents to read it |
| `recall save "<fact>"` | Append a dated entry to the memory file |
| `recall load` | Print the project's live memory |
| `recall review [--days 30]` | List numbered memories old enough to review |
| `recall keep <number>` | Keep a memory from the latest review and refresh its date |
| `recall archive <number>` | Move a memory from the latest review into `.recall/archive.md` |

## License

MIT

Made by [bchop-studio](https://github.com/bchop-studio)

Built for people tired of telling their agents the same thing twice.

If this helped, ⭐ the repository so others can find it.
