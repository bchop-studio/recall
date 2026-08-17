"""Tests for the recall memory store."""

from __future__ import annotations

from pathlib import Path

import pytest

from recall.memory import MemoryStore


@pytest.fixture
def store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(tmp_path)


def test_default_memory_file_location(store: MemoryStore) -> None:
    assert store.memory_file.relative_to(store.root) == Path(".recall/memory.md")


def test_save_creates_file_with_header(store: MemoryStore) -> None:
    entry = store.save("I'm building recall for Hermes agents.")
    assert store.memory_file.exists()
    text = store.memory_file.read_text()
    assert "# recall — project memory" in text
    assert "I'm building recall for Hermes agents." in text


def test_save_returns_entry_with_timestamp(store: MemoryStore) -> None:
    entry = store.save("some fact")
    assert "some fact" in entry.text
    assert entry.date


def test_load_returns_what_was_saved(store: MemoryStore) -> None:
    store.save("first fact")
    store.save("second fact")
    text = store.load()
    assert "first fact" in text
    assert "second fact" in text


def test_load_empty_when_no_file(store: MemoryStore) -> None:
    assert store.load() == ""


def test_init_creates_memory_file(store: MemoryStore) -> None:
    store.init()
    assert store.memory_file.exists()
    assert "# recall — project memory" in store.memory_file.read_text()


def test_init_is_idempotent(store: MemoryStore) -> None:
    store.init()
    store.init()
    # No duplicate headers on a second init
    text = store.memory_file.read_text()
    assert text.count("# recall — project memory") == 1


def test_save_groups_under_today_date(store: MemoryStore) -> None:
    store.save("one")
    store.save("two")
    text = store.memory_file.read_text()
    # Both entries appear under a single dated section
    import datetime

    today = datetime.date.today().isoformat()
    assert f"## {today}" in text
    assert "one" in text
    assert "two" in text
