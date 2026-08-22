"""The recall memory store: a per-project, dated, plain-text memory.

The store owns one file, ``.recall/memory.md``, in the project root. It is a
simple dated markdown list, deliberately dumb so any agent (Hermes, Claude
Code, Codex, or a future one) can read it without any tooling.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

HEADER = "# recall — project memory"


@dataclass(frozen=True)
class Entry:
    """A single saved memory with the date it was written."""

    text: str
    date: str
    line_index: int = field(default=-1, compare=False, repr=False)
    end_index: int = field(default=-1, compare=False, repr=False)
    raw_line: str = field(default="", compare=False, repr=False)
    raw_block: tuple[str, ...] = field(default=(), compare=False, repr=False)
    heading_index: int | None = field(default=None, compare=False, repr=False)


class MemoryStore:
    """Read, write, and initialize the per-project memory file."""

    RELATIVE_PATH = Path(".recall/memory.md")
    ARCHIVE_RELATIVE_PATH = Path(".recall/archive.md")
    REVIEW_RELATIVE_PATH = Path(".recall/review.json")
    LOCK_RELATIVE_PATH = Path(".recall/memory.lock")

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.memory_file = self.root / self.RELATIVE_PATH
        self.archive_file = self.root / self.ARCHIVE_RELATIVE_PATH
        self.review_file = self.root / self.REVIEW_RELATIVE_PATH
        self.lock_file = self.root / self.LOCK_RELATIVE_PATH

    def save(self, text: str) -> Entry:
        """Append a dated entry to the memory file, creating it if needed."""
        text = text.strip()
        if not text:
            raise ValueError("cannot save an empty memory")
        if "\n" in text or "\r" in text:
            raise ValueError("memory must be a single line")
        with self._locked():
            today = datetime.date.today().isoformat()
            if not self.memory_file.exists():
                self._init_unlocked()
            entry = Entry(text=text, date=today)
            updated = self._add_dated_entry_text(self.memory_file.read_text(), entry)
            self._atomic_write(self.memory_file, updated)
        return entry

    def load(self) -> str:
        """Return the full memory file text, or an empty string if none."""
        if not self.memory_file.exists():
            return ""
        return self.memory_file.read_text()

    def review(
        self, days: int = 30, today: datetime.date | None = None
    ) -> list[Entry]:
        """Return memories old enough to need a freshness review."""
        with self._locked():
            return self._review_unlocked(days=days, today=today)

    def _review_unlocked(
        self, days: int = 30, today: datetime.date | None = None
    ) -> list[Entry]:
        if days < 0:
            raise ValueError("review days cannot be negative")
        today = today or datetime.date.today()
        if not self.memory_file.exists():
            self._write_review_snapshot("", [], days, today)
            return []
        memory_text = self.memory_file.read_text()
        entries = self._scan_entries(memory_text, days, today)
        self._write_review_snapshot(memory_text, entries, days, today)
        return entries

    def keep_reviewed(self, number: int) -> Entry:
        """Keep one entry from the latest review snapshot."""
        with self._locked():
            entry = self._reviewed_entry(number)
            refreshed = self._keep_entry(entry, datetime.date.today())
            self.review_file.unlink(missing_ok=True)
            return refreshed

    def archive_reviewed(self, number: int) -> Entry:
        """Archive one entry from the latest review snapshot."""
        with self._locked():
            entry = self._reviewed_entry(number)
            archived = self._archive_entry(entry)
            self.review_file.unlink(missing_ok=True)
            return archived

    def keep(
        self,
        number: int,
        days: int = 30,
        today: datetime.date | None = None,
    ) -> Entry:
        """Confirm one numbered review entry and refresh its date."""
        today = today or datetime.date.today()
        with self._locked():
            entries = self._review_unlocked(days=days, today=today)
            if number < 1 or number > len(entries):
                raise IndexError("memory number is not in the review list")
            return self._keep_entry(entries[number - 1], today)

    def archive(
        self,
        number: int,
        days: int = 30,
        today: datetime.date | None = None,
    ) -> Entry:
        """Move one numbered review entry out of live agent memory."""
        with self._locked():
            entries = self._review_unlocked(days=days, today=today)
            if number < 1 or number > len(entries):
                raise IndexError("memory number is not in the review list")
            return self._archive_entry(entries[number - 1])

    def _keep_entry(self, entry: Entry, today: datetime.date) -> Entry:
        current_date = today.isoformat()
        refreshed = Entry(
            text=entry.text,
            date=current_date,
            raw_block=entry.raw_block,
        )
        updated = self._without_entry(entry)
        updated = self._add_dated_entry_text(updated, refreshed)
        self._atomic_write(self.memory_file, updated)
        return refreshed

    def _archive_entry(self, entry: Entry) -> Entry:
        self.archive_file.parent.mkdir(parents=True, exist_ok=True)
        archive_existed = self.archive_file.exists()
        archive_before = (
            self.archive_file.read_text()
            if archive_existed
            else "# recall — archived memory\n"
        )
        archive_after = self._add_dated_entry_text(archive_before, entry)
        live_after = self._without_entry(entry)
        self._atomic_write(self.archive_file, archive_after)
        try:
            self._atomic_write(self.memory_file, live_after)
        except BaseException:
            if archive_existed:
                self._atomic_write(self.archive_file, archive_before)
            else:
                self.archive_file.unlink(missing_ok=True)
            raise
        return entry

    @staticmethod
    def _scan_entries(
        memory_text: str, days: int, today: datetime.date
    ) -> list[Entry]:
        cutoff = today - datetime.timedelta(days=days)
        lines = memory_text.splitlines()
        entries: list[Entry] = []
        current_date: str | None = None
        current_heading_index: int | None = None
        index = 0
        while index < len(lines):
            line = lines[index]
            if line.startswith("## "):
                current_date = line[3:].strip()
                current_heading_index = index
                index += 1
                continue
            if not line.startswith("- "):
                index += 1
                continue
            start = index
            index += 1
            while index < len(lines):
                if lines[index].startswith("- ") or lines[index].startswith("## "):
                    break
                index += 1
            entry_date_label = current_date or "undated"
            try:
                entry_date = datetime.date.fromisoformat(entry_date_label)
                needs_review = entry_date <= cutoff
            except ValueError:
                needs_review = True
            if needs_review:
                raw_block = tuple(lines[start:index])
                entries.append(
                    Entry(
                        text=line[2:].rstrip(),
                        date=entry_date_label,
                        line_index=start,
                        end_index=index,
                        raw_line=line,
                        raw_block=raw_block,
                        heading_index=current_heading_index,
                    )
                )
        return entries

    @staticmethod
    def _entry_record(entry: Entry) -> dict[str, object]:
        return {
            "text": entry.text,
            "date": entry.date,
            "line_index": entry.line_index,
            "end_index": entry.end_index,
            "raw_line": entry.raw_line,
            "raw_block": list(entry.raw_block),
            "heading_index": entry.heading_index,
        }

    def _write_review_snapshot(
        self,
        memory_text: str,
        entries: list[Entry],
        days: int,
        today: datetime.date,
    ) -> None:
        snapshot = {
            "memory_sha256": self._fingerprint(memory_text),
            "days": days,
            "reviewed_on": today.isoformat(),
            "entries": [self._entry_record(entry) for entry in entries],
        }
        canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
        snapshot["snapshot_sha256"] = self._fingerprint(canonical)
        self._atomic_write(
            self.review_file,
            json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
        )

    def _reviewed_entry(self, number: int) -> Entry:
        if not self.review_file.exists():
            raise ValueError("no review snapshot; run recall review first")
        try:
            snapshot = json.loads(self.review_file.read_text())
            expected_snapshot_fingerprint = snapshot["snapshot_sha256"]
            payload = {
                key: value
                for key, value in snapshot.items()
                if key != "snapshot_sha256"
            }
            canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            if self._fingerprint(canonical) != expected_snapshot_fingerprint:
                raise ValueError("review snapshot changed; run recall review again")
            records = snapshot["entries"]
            expected_fingerprint = snapshot["memory_sha256"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ValueError("invalid review snapshot; run recall review again") from exc
        memory_text = self.load()
        if self._fingerprint(memory_text) != expected_fingerprint:
            raise ValueError("memory changed since review; run recall review again")
        try:
            days = int(snapshot["days"])
            reviewed_on = datetime.date.fromisoformat(str(snapshot["reviewed_on"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid review snapshot; run recall review again") from exc
        expected_records = [
            self._entry_record(entry)
            for entry in self._scan_entries(memory_text, days, reviewed_on)
        ]
        if records != expected_records:
            raise ValueError("review snapshot does not match memory; run recall review again")
        if number < 1 or number > len(records):
            raise IndexError("memory number is not in the review list")
        record = records[number - 1]
        try:
            return Entry(
                text=str(record["text"]),
                date=str(record["date"]),
                line_index=int(record["line_index"]),
                end_index=int(record["end_index"]),
                raw_line=str(record["raw_line"]),
                raw_block=tuple(str(line) for line in record["raw_block"]),
                heading_index=(
                    None
                    if record["heading_index"] is None
                    else int(record["heading_index"])
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid review snapshot; run recall review again") from exc

    @staticmethod
    def _fingerprint(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def init(self) -> None:
        """Create the memory file with a header if it doesn't exist."""
        with self._locked():
            self._init_unlocked()

    def _init_unlocked(self) -> None:
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.memory_file.exists():
            self.memory_file.write_text(f"{HEADER}\n")

    @staticmethod
    def _add_dated_entry_text(text: str, entry: Entry) -> str:
        lines = text.splitlines()
        entry_lines = list(entry.raw_block) or [f"- {entry.text}"]
        heading = f"## {entry.date}"
        if heading not in lines:
            prefix = "\n".join(lines).rstrip()
            return prefix + f"\n\n{heading}\n" + "\n".join(entry_lines) + "\n"
        heading_index = lines.index(heading)
        insert_at = next(
            (
                index
                for index in range(heading_index + 1, len(lines))
                if lines[index].startswith("## ")
            ),
            len(lines),
        )
        while insert_at > heading_index + 1 and not lines[insert_at - 1].strip():
            insert_at -= 1
        lines[insert_at:insert_at] = entry_lines
        return "\n".join(lines).rstrip() + "\n"

    @contextmanager
    def _locked(self):
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        lock_handle = self.lock_file.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                lock_handle.seek(0, os.SEEK_END)
                if lock_handle.tell() == 0:
                    lock_handle.write(b"\0")
                    lock_handle.flush()
                lock_handle.seek(0)
                msvcrt.locking(lock_handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if os.name == "nt":
                    import msvcrt

                    lock_handle.seek(0)
                    msvcrt.locking(lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        finally:
            lock_handle.close()

    @staticmethod
    def _atomic_write(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(text)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(temp_name, path)
        except BaseException:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
            raise

    def _without_entry(self, entry: Entry) -> str:
        lines = self.memory_file.read_text().splitlines()
        if (
            entry.line_index < 0
            or entry.end_index <= entry.line_index
            or entry.end_index > len(lines)
            or tuple(lines[entry.line_index : entry.end_index]) != entry.raw_block
        ):
            raise ValueError("selected memory changed; run recall review again")
        kept = lines[:entry.line_index] + lines[entry.end_index :]

        heading_index = entry.heading_index
        if (
            heading_index is not None
            and 0 <= heading_index < len(kept)
            and kept[heading_index].startswith("## ")
        ):
            next_heading = next(
                (
                    index
                    for index in range(heading_index + 1, len(kept))
                    if kept[index].startswith("## ")
                ),
                len(kept),
            )
            if not any(line.strip() for line in kept[heading_index + 1 : next_heading]):
                del kept[heading_index]
                if (
                    0 < heading_index < len(kept)
                    and not kept[heading_index - 1]
                    and not kept[heading_index]
                ):
                    del kept[heading_index]

        return "\n".join(kept).rstrip() + "\n"
