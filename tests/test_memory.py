"""Tests for the recall memory store."""

from __future__ import annotations

from pathlib import Path

import pytest

from recall.memory import Entry, MemoryStore


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


def test_save_rejects_multiline_memory(store: MemoryStore) -> None:
    with pytest.raises(ValueError, match="single line"):
        store.save("first line\ncontinuation line")


def test_archive_preserves_complete_legacy_multiline_entry(store: MemoryStore) -> None:
    import datetime

    store.init()
    store.memory_file.write_text(
        "# recall — project memory\n\n"
        "## 2026-06-01\n"
        "- first line\n"
        "continuation line\n"
        "- next fact\n"
    )
    store.review(days=30, today=datetime.date(2026, 8, 21))

    store.archive_reviewed(1)

    assert "first line" not in store.load()
    assert "continuation line" not in store.load()
    assert "next fact" in store.load()
    archive = store.archive_file.read_text()
    assert "- first line\ncontinuation line" in archive


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


def test_review_returns_only_entries_older_than_cutoff(store: MemoryStore) -> None:
    import datetime

    store.init()
    store.memory_file.write_text(
        "# recall — project memory\n\n"
        "## 2026-06-01\n- old fact\n\n"
        "## 2026-08-15\n- fresh fact\n"
    )

    entries = store.review(days=30, today=datetime.date(2026, 8, 21))

    assert entries == [Entry(text="old fact", date="2026-06-01")]


def test_review_includes_undated_and_malformed_sections(store: MemoryStore) -> None:
    import datetime

    store.init()
    store.memory_file.write_text(
        "# recall — project memory\n"
        "- loose fact\n\n"
        "## notes\n- malformed date fact\n\n"
        "## 2026-08-20\n- fresh fact\n"
    )

    entries = store.review(days=30, today=datetime.date(2026, 8, 21))

    assert [(entry.text, entry.date) for entry in entries] == [
        ("loose fact", "undated"),
        ("malformed date fact", "notes"),
    ]


def test_archive_moves_reviewed_entry_out_of_live_memory(store: MemoryStore) -> None:
    import datetime

    store.init()
    store.memory_file.write_text(
        "# recall — project memory\n\n"
        "## 2026-06-01\n- old fact\n\n"
        "## 2026-08-15\n- fresh fact\n"
    )

    archived = store.archive(1, days=30, today=datetime.date(2026, 8, 21))

    assert archived == Entry(text="old fact", date="2026-06-01")
    assert "old fact" not in store.load()
    assert "## 2026-06-01" not in store.load()
    assert "fresh fact" in store.load()
    assert "\n\n\n" not in store.load()
    assert "old fact" in store.archive_file.read_text()


def test_keep_refreshes_reviewed_entry_date(store: MemoryStore) -> None:
    import datetime

    store.init()
    store.memory_file.write_text(
        "# recall — project memory\n\n## 2026-06-01\n- still true\n"
    )

    kept = store.keep(1, days=30, today=datetime.date(2026, 8, 21))

    assert kept == Entry(text="still true", date="2026-08-21")
    assert store.review(days=30, today=datetime.date(2026, 8, 21)) == []
    assert "## 2026-08-21\n- still true" in store.load()
    assert "\n\n\n" not in store.load()


def test_keep_preserves_live_memory_when_write_fails(
    store: MemoryStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    import datetime

    store.init()
    original = "# recall — project memory\n\n## 2026-06-01\n- still true\n"
    store.memory_file.write_text(original)
    store.review(days=30, today=datetime.date(2026, 8, 21))

    def fail_write(_path: Path, _text: str) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(store, "_atomic_write", fail_write)

    with pytest.raises(OSError, match="disk full"):
        store.keep_reviewed(1)

    assert store.load() == original


def test_keep_does_not_overwrite_a_concurrent_save(
    store: MemoryStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    import datetime
    import threading

    store.init()
    store.memory_file.write_text(
        "# recall — project memory\n\n## 2026-06-01\n- still true\n"
    )
    store.review(days=30, today=datetime.date(2026, 8, 21))
    entered_write_window = threading.Event()
    release_keep = threading.Event()
    save_finished = threading.Event()
    original_without_entry = store._without_entry

    def pause_after_read(entry: Entry) -> str:
        updated = original_without_entry(entry)
        entered_write_window.set()
        assert release_keep.wait(timeout=2)
        return updated

    monkeypatch.setattr(store, "_without_entry", pause_after_read)
    keep_thread = threading.Thread(target=lambda: store.keep_reviewed(1))
    keep_thread.start()
    assert entered_write_window.wait(timeout=2)

    def concurrent_save() -> None:
        MemoryStore(store.root).save("concurrent save")
        save_finished.set()

    save_thread = threading.Thread(target=concurrent_save)
    save_thread.start()
    assert not save_finished.wait(timeout=0.1)
    release_keep.set()
    keep_thread.join(timeout=2)
    save_thread.join(timeout=2)

    assert not keep_thread.is_alive()
    assert not save_thread.is_alive()
    assert "still true" in store.load()
    assert "concurrent save" in store.load()


def test_archive_does_not_overwrite_a_concurrent_save(
    store: MemoryStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    import datetime
    import threading

    store.init()
    store.memory_file.write_text(
        "# recall — project memory\n\n## 2026-06-01\n- archive me\n"
    )
    store.review(days=30, today=datetime.date(2026, 8, 21))
    entered_write_window = threading.Event()
    release_archive = threading.Event()
    save_finished = threading.Event()
    original_without_entry = store._without_entry

    def pause_after_read(entry: Entry) -> str:
        updated = original_without_entry(entry)
        entered_write_window.set()
        assert release_archive.wait(timeout=2)
        return updated

    monkeypatch.setattr(store, "_without_entry", pause_after_read)
    archive_thread = threading.Thread(target=lambda: store.archive_reviewed(1))
    archive_thread.start()
    assert entered_write_window.wait(timeout=2)

    def concurrent_save() -> None:
        MemoryStore(store.root).save("concurrent save")
        save_finished.set()

    save_thread = threading.Thread(target=concurrent_save)
    save_thread.start()
    assert not save_finished.wait(timeout=0.1)
    release_archive.set()
    archive_thread.join(timeout=2)
    save_thread.join(timeout=2)

    assert not archive_thread.is_alive()
    assert not save_thread.is_alive()
    assert "archive me" not in store.load()
    assert "concurrent save" in store.load()
    assert "archive me" in store.archive_file.read_text()


def test_archive_keeps_entries_under_their_original_dates(store: MemoryStore) -> None:
    import datetime

    store.init()
    store.memory_file.write_text(
        "# recall — project memory\n\n"
        "## 2026-06-01\n- june one\n- june two\n\n"
        "## 2026-07-01\n- july\n"
    )

    store.archive(1, days=30, today=datetime.date(2026, 8, 21))
    store.archive(2, days=30, today=datetime.date(2026, 8, 21))
    store.archive(1, days=30, today=datetime.date(2026, 8, 21))

    archive = store.archive_file.read_text()
    june_section = archive.split("## 2026-06-01", 1)[1].split("## 2026-07-01", 1)[0]
    assert "- june one" in june_section
    assert "- june two" in june_section


def test_archive_removes_exact_entry_with_trailing_whitespace(store: MemoryStore) -> None:
    import datetime

    store.init()
    store.memory_file.write_text(
        "# recall — project memory\n\n## 2026-06-01\n- spaced fact   \n"
    )

    store.archive(1, days=30, today=datetime.date(2026, 8, 21))

    assert "spaced fact" not in store.load()


def test_archive_preserves_live_memory_when_removal_write_fails(
    store: MemoryStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    import datetime

    store.init()
    original = "# recall — project memory\n\n## 2026-06-01\n- old fact\n"
    store.memory_file.write_text(original)
    real_atomic_write = store._atomic_write

    def fail_live_write(path: Path, text: str) -> None:
        if path == store.memory_file:
            raise OSError("disk full")
        real_atomic_write(path, text)

    monkeypatch.setattr(store, "_atomic_write", fail_live_write)

    with pytest.raises(OSError, match="disk full"):
        store.archive(1, days=30, today=datetime.date(2026, 8, 21))

    assert store.load() == original
    assert not store.archive_file.exists()


def test_archive_restores_existing_archive_when_live_write_fails(
    store: MemoryStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    import datetime

    store.init()
    live_before = "# recall — project memory\n\n## 2026-06-01\n- old fact\n"
    archive_before = "# recall — archived memory\n\n## 2026-05-01\n- earlier\n"
    store.memory_file.write_text(live_before)
    store.archive_file.write_text(archive_before)
    real_atomic_write = store._atomic_write

    def fail_live_write(path: Path, text: str) -> None:
        if path == store.memory_file:
            raise OSError("disk full")
        real_atomic_write(path, text)

    monkeypatch.setattr(store, "_atomic_write", fail_live_write)

    with pytest.raises(OSError, match="disk full"):
        store.archive(1, days=30, today=datetime.date(2026, 8, 21))

    assert store.load() == live_before
    assert store.archive_file.read_text() == archive_before


def test_archive_preserves_unrelated_prose_section_heading(store: MemoryStore) -> None:
    import datetime

    store.init()
    store.memory_file.write_text(
        "# recall — project memory\n\n"
        "## 2026-06-01\n- old fact\n\n"
        "## Notes\nimportant prose\n"
    )

    store.archive(1, days=30, today=datetime.date(2026, 8, 21))

    assert "## Notes\nimportant prose" in store.load()
