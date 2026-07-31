from __future__ import annotations

import json
from pathlib import Path

from .scanner import ProjectScanner


def print_summary(model) -> None:
    print("=" * 60)
    print("HYB AI INDEX")
    print("=" * 60)

    print(f"Root              : {model.root}")
    print(f"Directories       : {model.total_directories}")
    print(f"Python Files      : {model.total_python}")
    print(f"Markdown Files    : {model.total_markdown}")
    print(f"Config Files      : {model.total_config}")
    print(f"Entry Points      : {model.total_entry_points}")
    print(f"Domains           : {len(model.domains)}")

    print()

    if model.entry_points:
        print("Entry Points")
        print("-" * 40)

        for entry in model.entry_points:
            print(
                f"{entry.path.relative_to(model.root)}"
                f" ({entry.reason})"
            )

        print()

    if model.domains:
        print("Detected Domains")
        print("-" * 40)

        for domain in model.domains:
            print(
                f"{domain.name:20}"
                f"{len(domain.files):4} files"
            )


def build_project_map(model) -> dict:

    project = {}

    project["root"] = str(model.root)

    project["statistics"] = {
        "directories": model.total_directories,
        "python_files": model.total_python,
        "markdown_files": model.total_markdown,
        "config_files": model.total_config,
        "entry_points": model.total_entry_points,
    }

    project["entry_points"] = [
        {
            "path": str(
                entry.path.relative_to(model.root)
            ),
            "reason": entry.reason,
        }
        for entry in model.entry_points
    ]

    project["domains"] = {
        domain.name: [
            str(file.relative_to(model.root))
            for file in sorted(domain.files)
        ]
        for domain in model.domains
    }

    project["python_files"] = [
        {
            "path": str(
                file.path.relative_to(model.root)
            ),
            "classes": [
                class_reference.name
                for class_reference in file.classes
            ],
            "functions": [
                function_reference.name
                for function_reference in (
                    file.analysis.iter_functions()
                    if file.analysis is not None
                    else ()
                )
            ],
        }
        for file in model.python_files
    ]

    project["documents"] = [
        {
            "path": str(
                file.path.relative_to(model.root)
            ),
            "title": file.title,
        }
        for file in model.markdown_files
    ]

    return project


def save_project_map(
    model,
    output: Path,
) -> None:

    data = build_project_map(model)

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output.open(
        "w",
        encoding="utf-8",
    ) as fp:

        json.dump(
            data,
            fp,
            indent=2,
            ensure_ascii=False,
        )


def generate_ai_index(model) -> str:

    lines = []

    lines.append("# AI_INDEX")
    lines.append("")
    lines.append("## Repository Summary")
    lines.append("")
    lines.append(
        f"- Directories : {model.total_directories}"
    )
    lines.append(
        f"- Python Files : {model.total_python}"
    )
    lines.append(
        f"- Markdown Files : {model.total_markdown}"
    )
    lines.append(
        f"- Config Files : {model.total_config}"
    )
    lines.append("")

    lines.append("## Entry Points")
    lines.append("")

    if model.entry_points:

        for entry in model.entry_points:

            lines.append(
                f"- `{entry.path.relative_to(model.root)}`"
                f" ({entry.reason})"
            )

    else:

        lines.append("- None")

    lines.append("")
    lines.append("## Domains")
    lines.append("")

    for domain in model.domains:

        lines.append(f"### {domain.name}")
        lines.append("")

        for file in sorted(domain.files):

            lines.append(
                f"- `{file.relative_to(model.root)}`"
            )

        lines.append("")

    return "\n".join(lines)


def save_ai_index(
    model,
    output: Path,
) -> None:

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.write_text(
        generate_ai_index(model),
        encoding="utf-8",
    )


def main():

    root = Path.cwd()

    scanner = ProjectScanner(root)

    model = scanner.scan()

    print_summary(model)

    save_project_map(
        model,
        root / "project_map.json",
    )

    save_ai_index(
        model,
        root / "ai_docs" / "AI_INDEX.md",
    )

    print()
    print("Generated:")
    print("  project_map.json")
    print("  ai_docs/AI_INDEX.md")


if __name__ == "__main__":
    main()
