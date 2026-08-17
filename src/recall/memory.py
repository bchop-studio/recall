"""The recall memory store: a per-project, dated, plain-text memory.

The store owns one file, ``.recall/memory.md``, in the project root. It is a
simple dated markdown list, deliberately dumb so any agent (Hermes, Claude
Code, Codex, or a future one) can read it without any tooling.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path

HEADER = "# recall — project memory"


@dataclass(frozen=True)
class Entry:
    """A single saved memory with the date it was written."""

    text: str
    date: str


class MemoryStore:
    """Read, write, and initialize the per-project memory file."""

    RELATIVE_PATH = Path(".recall/memory.md")

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.memory_file = self.root / self.RELATIVE_PATH

    def save(self, text: str) -> Entry:
        """Append a dated entry to the memory file, creating it if needed."""
        text = text.strip()
        if not text:
            raise ValueError("cannot save an empty memory")
        today = datetime.date.today().isoformat()
        if not self.memory_file.exists():
            self.init()
        # If today's section isn't present, add it.
        if f"## {today}" not in self.memory_file.read_text():
            self._append(f"\n## {today}\n")
        self._append(f"- {text}\n")
        return Entry(text=text, date=today)

    def load(self) -> str:
        """Return the full memory file text, or an empty string if none."""
        if not self.memory_file.exists():
            return ""
        return self.memory_file.read_text()

    def init(self) -> None:
        """Create the memory file with a header if it doesn't exist."""
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.memory_file.exists():
            self.memory_file.write_text(f"{HEADER}\n")

    def _append(self, text: str) -> None:
        with self.memory_file.open("a") as fh:
            fh.write(text)
