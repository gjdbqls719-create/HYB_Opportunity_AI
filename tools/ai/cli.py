from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from .query import KnowledgeQueryEngine, KnowledgeQueryResult
from .scanner import ProjectScanner


COMMAND_METHODS = {
    "query": "find_symbol",
    "deps": "dependencies",
    "impact": "analyze_impact",
    "who-uses": "reverse_dependencies",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hyb-ai",
        description="Query the HYB repository knowledge graph.",
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    for command in COMMAND_METHODS:
        command_parser = subparsers.add_parser(
            command,
            help=f"Run the {command} knowledge query.",
        )
        command_parser.add_argument(
            "target",
            help="Symbol, class, module, or repository-relative file path.",
        )
        output_group = command_parser.add_mutually_exclusive_group()
        output_group.add_argument(
            "--json",
            action="store_true",
            help="Print structured JSON output.",
        )
        output_group.add_argument(
            "--summary",
            action="store_true",
            help="Print a human-readable summary.",
        )

    return parser


def execute_query(
    engine: KnowledgeQueryEngine,
    *,
    command: str,
    target: str,
) -> KnowledgeQueryResult:
    method_name = COMMAND_METHODS[command]
    method = getattr(engine, method_name)
    return method(target)


def run_cli(
    argv: Sequence[str] | None = None,
    *,
    root: Path | None = None,
    output: TextIO = sys.stdout,
) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    repository_root = (
        root.resolve()
        if root is not None
        else Path.cwd().resolve()
    )
    project = ProjectScanner(repository_root).scan()
    engine = KnowledgeQueryEngine(project)
    result = execute_query(
        engine,
        command=arguments.command,
        target=arguments.target,
    )

    rendered = (
        result.to_json()
        if arguments.json
        else result.to_summary()
    )
    print(rendered, file=output)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())
