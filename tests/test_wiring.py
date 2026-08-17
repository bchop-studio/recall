"""Tests for the recall agent wiring."""

from __future__ import annotations

from pathlib import Path

import pytest

from recall.wiring import AgentWiring


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path


def test_hermes_and_codex_use_agents_md(root: Path) -> None:
    w = AgentWiring(root)
    assert w.file_for("hermes") == root / "AGENTS.md"
    assert w.file_for("codex") == root / "AGENTS.md"


def test_claude_uses_claude_md(root: Path) -> None:
    w = AgentWiring(root)
    assert w.file_for("claude") == root / "CLAUDE.md"


def test_unknown_agent_raises(root: Path) -> None:
    w = AgentWiring(root)
    with pytest.raises(ValueError):
        w.file_for("antigravity")


def test_known_agents_include_big_three(root: Path) -> None:
    w = AgentWiring(root)
    assert {"hermes", "claude", "codex"} <= set(w.known_agents())


def test_wire_adds_memory_pointer_to_new_file(root: Path) -> None:
    w = AgentWiring(root)
    w.wire("hermes")
    text = (root / "AGENTS.md").read_text()
    assert "recall" in text.lower()
    assert ".recall/memory.md" in text


def test_wire_is_idempotent(root: Path) -> None:
    w = AgentWiring(root)
    w.wire("hermes")
    first = (root / "AGENTS.md").read_text()
    w.wire("hermes")
    second = (root / "AGENTS.md").read_text()
    assert first == second


def test_wire_appends_to_existing_file_without_clobber(root: Path) -> None:
    (root / "AGENTS.md").write_text("# Existing rules\n\n- never commit to main\n")
    w = AgentWiring(root)
    w.wire("hermes")
    text = (root / "AGENTS.md").read_text()
    assert "# Existing rules" in text
    assert "- never commit to main" in text
    assert ".recall/memory.md" in text


def test_unsupported_agent_wire_raises(root: Path) -> None:
    w = AgentWiring(root)
    with pytest.raises(ValueError):
        w.wire("antigravity")
