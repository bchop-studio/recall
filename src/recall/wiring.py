"""Wire recall into the agents that read per-project instruction files.

Each coding agent reads a markdown file in the project root at session start:

- Hermes reads ``AGENTS.md``
- Codex reads ``AGENTS.md``
- Claude Code reads ``CLAUDE.md``

Wiring recall means ensuring that file carries a pointer to the memory file
so the agent loads it. The pointer is a small delimited block that we can add
or replace idempotently without clobbering whatever the project already has
in that file.
"""

from __future__ import annotations

from pathlib import Path

MEMORY_POINTER = (
    "## Recall memory\n\n"
    "Before starting work, read `.recall/memory.md`. It holds the project's "
    "living memory: who the user is and where the project stands. Refresh your "
    "context from it at the start of every session.\n"
)

# Which file each agent reads. One agent per known name; several agents may
# share a file (Hermes and Codex both read AGENTS.md).
_AGENT_FILES: dict[str, str] = {
    "hermes": "AGENTS.md",
    "claude": "CLAUDE.md",
    "codex": "AGENTS.md",
}

_BEGIN = "<!-- recall:start -->"
_END = "<!-- recall:end -->"


class AgentWiring:
    """Map agents to their instruction files and write the recall pointer."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def known_agents(self) -> set[str]:
        return set(_AGENT_FILES)

    def file_for(self, agent: str) -> Path:
        if agent not in _AGENT_FILES:
            raise ValueError(f"unknown agent: {agent!r}")
        return self.root / _AGENT_FILES[agent]

    def wire(self, agent: str) -> Path:
        """Ensure the recall pointer is present in the agent's file.

        Returns the path that was written. Idempotent: running twice leaves
        the file unchanged.
        """
        target = self.file_for(agent)
        block = f"{_BEGIN}\n{MEMORY_POINTER}{_END}\n"
        if target.exists():
            text = target.read_text()
            if _BEGIN in text:
                # Replace the existing recall block, consuming the newline that
                # trails the old end marker so the result is byte-identical.
                start = text.index(_BEGIN)
                end = text.index(_END) + len(_END)
                while end < len(text) and text[end] == "\n":
                    end += 1
                text = text[:start] + block + text[end:]
            else:
                text = text.rstrip() + "\n\n" + block
        else:
            text = block
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        return target
