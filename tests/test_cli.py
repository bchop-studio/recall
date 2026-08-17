"""Tests for the recall CLI."""

from __future__ import annotations

from pathlib import Path

from recall.cli import run


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


def test_init_wires_agents(tmp_path: Path) -> None:
    _run(tmp_path, "init")
    assert (tmp_path / ".recall" / "memory.md").exists()
    assert (tmp_path / "AGENTS.md").exists()
    assert (tmp_path / "CLAUDE.md").exists()


def test_load_before_any_save_is_empty(tmp_path: Path) -> None:
    out = _run(tmp_path, "load")
    assert out == ""


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
