"""The recall command-line interface.

``recall save`` remembers a fact, ``recall load`` prints the whole memory, and
``recall init`` sets up the memory file and wires Hermes, Claude Code, and
Codex to read it.
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

    sub.add_parser("save", help="Remember a fact about this project.")

    sub.add_parser("load", help="Print the project's full memory.")

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
    args, _unknown = parser.parse_known_args(argv)
    root = Path.cwd()

    if args.command == "save":
        # The fact is everything after `recall save`.
        text = " ".join(_raw_tail(argv))
        store = MemoryStore(root)
        store.save(text)
        print(f"remembered: {text}")
    elif args.command == "load":
        store = MemoryStore(root)
        out = store.load()
        if out:
            print(out, end="")
    elif args.command == "init":
        store = MemoryStore(root)
        store.init()
        wiring = AgentWiring(root)
        for agent in args.agents:
            wiring.wire(agent)
        print(f"created {store.memory_file}")
        print("wired agents → " + ", ".join(sorted(args.agents)))


def _raw_tail(argv: list[str]) -> list[str]:
    """Return everything after the subcommand verb."""
    try:
        idx = argv.index("save") + 1
    except ValueError:
        return []
    return argv[idx:]


def main() -> None:
    run(sys.argv[1:])


if __name__ == "__main__":  # pragma: no cover
    main()
