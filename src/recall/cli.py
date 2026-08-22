"""The recall command-line interface.

``recall save`` remembers a fact, ``recall load`` prints live memory,
``recall review`` creates a numbered freshness snapshot, and ``recall keep`` or
``recall archive`` resolve one reviewed entry. ``recall init`` wires Hermes,
Claude Code, and Codex to read the project memory.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from recall.memory import MemoryStore
from recall.wiring import AgentWiring

DEFAULT_AGENTS = ("hermes", "claude", "codex")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="recall",
        description="Give your agents a living per-project memory.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    save = sub.add_parser("save", help="Remember a fact about this project.")
    save.add_argument("text", nargs="+", help="The single-line fact to remember.")

    sub.add_parser("load", help="Print the project's full memory.")

    review = sub.add_parser("review", help="List memories that may be stale.")
    review.add_argument(
        "--days",
        type=int,
        default=30,
        help="Review memories this many days old (default: 30).",
    )

    archive = sub.add_parser(
        "archive", help="Move a numbered review memory out of live context."
    )
    archive.add_argument("number", type=int, help="Number shown by recall review.")

    keep = sub.add_parser("keep", help="Keep a memory and refresh its review date.")
    keep.add_argument("number", type=int, help="Number shown by recall review.")

    init = sub.add_parser(
        "init", help="Create the memory file and wire agents to read it."
    )
    init.add_argument(
        "--agents",
        nargs="*",
        default=list(DEFAULT_AGENTS),
        help="Which agents to wire (default: hermes, claude, codex).",
    )
    return parser


def run(argv: list[str]) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path.cwd()

    if args.command == "save":
        text = " ".join(args.text)
        store = MemoryStore(root)
        try:
            store.save(text)
        except ValueError as exc:
            parser.error(str(exc))
        print(f"remembered: {text}")
    elif args.command == "load":
        store = MemoryStore(root)
        out = store.load()
        if out:
            print(out, end="")
    elif args.command == "review":
        store = MemoryStore(root)
        try:
            entries = store.review(days=args.days)
        except ValueError as exc:
            parser.error(str(exc))
        if not entries:
            print("no memories need review")
        for number, entry in enumerate(entries, start=1):
            print(f"{number}. [{entry.date}] {entry.text}")
    elif args.command == "archive":
        store = MemoryStore(root)
        try:
            entry = store.archive_reviewed(args.number)
        except (IndexError, ValueError) as exc:
            parser.error(str(exc))
        print(f"archived: {entry.text}")
    elif args.command == "keep":
        store = MemoryStore(root)
        try:
            entry = store.keep_reviewed(args.number)
        except (IndexError, ValueError) as exc:
            parser.error(str(exc))
        print(f"kept: {entry.text}")
    elif args.command == "init":
        store = MemoryStore(root)
        store.init()
        wiring = AgentWiring(root)
        for agent in args.agents:
            wiring.wire(agent)
        print(f"created {store.memory_file}")
        print("wired agents → " + ", ".join(sorted(args.agents)))


def main() -> None:
    run(sys.argv[1:])


if __name__ == "__main__":  # pragma: no cover
    main()
