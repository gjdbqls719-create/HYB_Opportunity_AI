from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pytest

from tools.ai.cli import build_parser, run_cli


def build_cli_repository(root: Path) -> None:
    app_directory = root / "app"
    tests_directory = root / "tests"
    app_directory.mkdir()
    tests_directory.mkdir()

    (app_directory / "__init__.py").write_text(
        "",
        encoding="utf-8",
    )
    (app_directory / "models.py").write_text(
        "class Product:\n"
        "    pass\n",
        encoding="utf-8",
    )
    (app_directory / "service.py").write_text(
        "from app.models import Product\n\n"
        "def build_product() -> Product:\n"
        "    return Product()\n",
        encoding="utf-8",
    )
    (tests_directory / "test_models.py").write_text(
        "from app.models import Product\n\n"
        "def test_product() -> None:\n"
        "    assert Product() is not None\n",
        encoding="utf-8",
    )


@pytest.fixture
def cli_root(tmp_path: Path) -> Path:
    build_cli_repository(tmp_path)
    return tmp_path


@pytest.mark.parametrize(
    ("command", "expected_query_type"),
    [
        ("query", "symbol_query"),
        ("deps", "dependency_query"),
        ("impact", "impact_analysis"),
        ("who-uses", "reverse_dependency_query"),
    ],
)
def test_cli_commands_return_structured_json(
    cli_root: Path,
    command: str,
    expected_query_type: str,
) -> None:
    output = StringIO()

    exit_code = run_cli(
        [command, "Product", "--json"],
        root=cli_root,
        output=output,
    )
    payload = json.loads(output.getvalue())

    assert exit_code == 0
    assert payload["query_type"] == expected_query_type
    assert payload["target"] == "Product"


def test_cli_defaults_to_human_readable_summary(
    cli_root: Path,
) -> None:
    output = StringIO()

    exit_code = run_cli(
        ["query", "Product"],
        root=cli_root,
        output=output,
    )

    assert exit_code == 0
    assert "Symbol Query: Product" in output.getvalue()
    assert "class Product (app/models.py:1)" in output.getvalue()


def test_cli_accepts_explicit_summary_option(
    cli_root: Path,
) -> None:
    output = StringIO()

    exit_code = run_cli(
        ["who-uses", "Product", "--summary"],
        root=cli_root,
        output=output,
    )

    assert exit_code == 0
    assert "Reverse Dependency Query: Product" in output.getvalue()
    assert "app/service.py" in output.getvalue()


def test_cli_parser_uses_public_command_name() -> None:
    assert build_parser().prog == "hyb-ai"


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["unknown", "Product"],
        ["query"],
        ["query", "Product", "--json", "--summary"],
    ],
)
def test_cli_rejects_invalid_commands_and_missing_arguments(
    argv: list[str],
) -> None:
    with pytest.raises(SystemExit) as captured:
        run_cli(argv)

    assert captured.value.code == 2
