"""Tests for the recall CLI."""

from __future__ import annotations

from pathlib import Path

import pytest

import recall
from recall.cli import run


def test_package_version_is_0_2_0() -> None:
    assert recall.__version__ == "0.2.0"


def _run(tmp: Path, *args: str) -> str:
    """Run the CLI in a scratch dir and return stdout."""
    import io
    import os
    import sys

    old_cwd = Path.cwd()
    old_stdout = sys.stdout
    try:
        sys.stdout = io.StringIO()
        os.chdir(tmp)
        try:
            run(list(args))
        except SystemExit as exc:  # pragma: no cover - defensive
            if exc.code != 0:
                raise
        return sys.stdout.getvalue()
    finally:
        sys.stdout = old_stdout
        os.chdir(old_cwd)


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    _run(tmp_path, "save", "remember this fact")
    out = _run(tmp_path, "load")
    assert "remember this fact" in out


def test_save_rejects_multiline_text_without_writing(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        _run(tmp_path, "save", "first line\ncontinuation line")

    assert exc.value.code == 2
    assert not (tmp_path / ".recall" / "memory.md").exists()


def test_init_wires_agents(tmp_path: Path) -> None:
    _run(tmp_path, "init")
    assert (tmp_path / ".recall" / "memory.md").exists()
    assert (tmp_path / "AGENTS.md").exists()
    assert (tmp_path / "CLAUDE.md").exists()


def test_load_before_any_save_is_empty(tmp_path: Path) -> None:
    out = _run(tmp_path, "load")
    assert out == ""


def test_review_lists_old_memories_with_numbers(tmp_path: Path) -> None:
    memory = tmp_path / ".recall" / "memory.md"
    memory.parent.mkdir()
    memory.write_text(
        "# recall — project memory\n\n## 2000-01-01\n- stale fact\n"
    )

    out = _run(tmp_path, "review")

    assert "1. [2000-01-01] stale fact" in out


def test_archive_moves_numbered_review_memory(tmp_path: Path) -> None:
    memory = tmp_path / ".recall" / "memory.md"
    memory.parent.mkdir()
    memory.write_text(
        "# recall — project memory\n\n## 2000-01-01\n- stale fact\n"
    )

    _run(tmp_path, "review")
    out = _run(tmp_path, "archive", "1")

    assert "archived: stale fact" in out
    assert "stale fact" not in memory.read_text()
    assert "stale fact" in (tmp_path / ".recall" / "archive.md").read_text()


def test_keep_refreshes_numbered_review_memory(tmp_path: Path) -> None:
    memory = tmp_path / ".recall" / "memory.md"
    memory.parent.mkdir()
    memory.write_text(
        "# recall — project memory\n\n## 2000-01-01\n- still true\n"
    )

    _run(tmp_path, "review")
    out = _run(tmp_path, "keep", "1")

    assert "kept: still true" in out
    assert _run(tmp_path, "review") == "no memories need review\n"


def test_archive_rejects_a_number_not_shown_by_review(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        _run(tmp_path, "archive", "1")

    assert exc.value.code == 2


def test_review_rejects_negative_days(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        _run(tmp_path, "review", "--days", "-1")

    assert exc.value.code == 2


def test_archive_uses_the_numbered_review_snapshot(tmp_path: Path) -> None:
    import datetime

    memory = tmp_path / ".recall" / "memory.md"
    memory.parent.mkdir()
    today = datetime.date.today()
    forty_two_days_old = (today - datetime.timedelta(days=42)).isoformat()
    one_hundred_days_old = (today - datetime.timedelta(days=100)).isoformat()
    memory.write_text(
        "# recall — project memory\n\n"
        f"## {forty_two_days_old}\n- newer stale fact\n\n"
        f"## {one_hundred_days_old}\n- very old fact\n"
    )

    review = _run(tmp_path, "review", "--days", "90")
    assert "1. " in review and "very old fact" in review
    assert "newer stale fact" not in review

    _run(tmp_path, "archive", "1")

    assert "newer stale fact" in memory.read_text()
    assert "very old fact" not in memory.read_text()


def test_archive_rejects_unknown_options_without_mutating(tmp_path: Path) -> None:
    memory = tmp_path / ".recall" / "memory.md"
    memory.parent.mkdir()
    original = "# recall — project memory\n\n## 2000-01-01\n- old fact\n"
    memory.write_text(original)
    _run(tmp_path, "review")

    with pytest.raises(SystemExit) as exc:
        _run(tmp_path, "archive", "1", "--dayz", "90")

    assert exc.value.code == 2
    assert memory.read_text() == original


def test_archive_rejects_a_stale_review_snapshot(tmp_path: Path) -> None:
    memory = tmp_path / ".recall" / "memory.md"
    memory.parent.mkdir()
    original = "# recall — project memory\n\n## 2000-01-01\n- old fact\n"
    memory.write_text(original)
    _run(tmp_path, "review")
    memory.write_text(original + "- changed after review\n")

    with pytest.raises(SystemExit) as exc:
        _run(tmp_path, "archive", "1")

    assert exc.value.code == 2
    assert "old fact" in memory.read_text()
    assert not (tmp_path / ".recall" / "archive.md").exists()


def test_archive_requires_a_fresh_review_after_each_change(tmp_path: Path) -> None:
    memory = tmp_path / ".recall" / "memory.md"
    memory.parent.mkdir()
    memory.write_text(
        "# recall — project memory\n\n## 2000-01-01\n- first\n- second\n"
    )
    _run(tmp_path, "review")
    _run(tmp_path, "archive", "1")

    with pytest.raises(SystemExit) as exc:
        _run(tmp_path, "archive", "1")

    assert exc.value.code == 2
    assert "second" in memory.read_text()


def test_archive_rejects_a_tampered_review_record(tmp_path: Path) -> None:
    import json

    memory = tmp_path / ".recall" / "memory.md"
    memory.parent.mkdir()
    original = "# recall — project memory\n\n## 2000-01-01\n- real fact\n"
    memory.write_text(original)
    _run(tmp_path, "review")
    review_file = tmp_path / ".recall" / "review.json"
    snapshot = json.loads(review_file.read_text())
    snapshot["entries"][0]["text"] = "forged fact"
    review_file.write_text(json.dumps(snapshot))

    with pytest.raises(SystemExit) as exc:
        _run(tmp_path, "archive", "1")

    assert exc.value.code == 2
    assert memory.read_text() == original
    assert not (tmp_path / ".recall" / "archive.md").exists()


def test_init_is_safe_to_run_twice(tmp_path: Path) -> None:
    _run(tmp_path, "init")
    agents = (tmp_path / "AGENTS.md").read_text()
    _run(tmp_path, "init")
    assert (tmp_path / "AGENTS.md").read_text() == agents


def test_unknown_command_raises(tmp_path: Path) -> None:
    import os

    import pytest

    old_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        with pytest.raises(SystemExit):
            run(["frobnicate"])
    finally:
        os.chdir(old_cwd)
