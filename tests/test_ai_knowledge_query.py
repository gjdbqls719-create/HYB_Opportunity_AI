from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.ai.query import KnowledgeQueryEngine
from tools.ai.scanner import ProjectScanner


def build_query_repository(root: Path) -> None:
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
        "    def identity(self) -> str:\n"
        "        return 'product'\n",
        encoding="utf-8",
    )
    (app_directory / "repository.py").write_text(
        "from app.models import Product\n\n"
        "class ProductRepository:\n"
        "    def get(self) -> Product:\n"
        "        return Product()\n",
        encoding="utf-8",
    )
    (app_directory / "service.py").write_text(
        "from app.repository import ProductRepository\n\n"
        "def load_product() -> str:\n"
        "    repository = ProductRepository()\n"
        "    return repository.get().identity()\n",
        encoding="utf-8",
    )
    (app_directory / "cli.py").write_text(
        "from app.service import load_product\n\n"
        "def main() -> str:\n"
        "    return load_product()\n",
        encoding="utf-8",
    )
    (tests_directory / "test_models.py").write_text(
        "from app.models import Product\n\n"
        "def test_product() -> None:\n"
        "    assert Product().identity() == 'product'\n",
        encoding="utf-8",
    )
    (tests_directory / "test_service.py").write_text(
        "from app.service import load_product\n\n"
        "def test_load_product() -> None:\n"
        "    assert load_product() == 'product'\n",
        encoding="utf-8",
    )


def build_duplicate_symbol_repository(root: Path) -> None:
    app_directory = root / "app"
    app_directory.mkdir()

    (app_directory / "__init__.py").write_text(
        "",
        encoding="utf-8",
    )
    (app_directory / "first.py").write_text(
        "class Shared:\n"
        "    pass\n",
        encoding="utf-8",
    )
    (app_directory / "second.py").write_text(
        "class Shared:\n"
        "    pass\n",
        encoding="utf-8",
    )
    (app_directory / "use_first.py").write_text(
        "from app.first import Shared\n\n"
        "FIRST = Shared()\n",
        encoding="utf-8",
    )
    (app_directory / "use_second.py").write_text(
        "from app.second import Shared\n\n"
        "SECOND = Shared()\n",
        encoding="utf-8",
    )


def build_circular_dependency_repository(root: Path) -> None:
    app_directory = root / "app"
    app_directory.mkdir()

    (app_directory / "__init__.py").write_text(
        "",
        encoding="utf-8",
    )
    (app_directory / "a.py").write_text(
        "from app.b import B\n\n"
        "class A:\n"
        "    pass\n",
        encoding="utf-8",
    )
    (app_directory / "b.py").write_text(
        "from app.a import A\n\n"
        "class B:\n"
        "    pass\n",
        encoding="utf-8",
    )
    (app_directory / "consumer.py").write_text(
        "from app.a import A\n\n"
        "VALUE = A()\n",
        encoding="utf-8",
    )


@pytest.fixture
def query_engine(tmp_path: Path) -> KnowledgeQueryEngine:
    build_query_repository(tmp_path)
    project = ProjectScanner(tmp_path).scan()
    return KnowledgeQueryEngine(project)


def test_symbol_query_returns_definitions_references_and_tests(
    query_engine: KnowledgeQueryEngine,
) -> None:
    result = query_engine.find_symbol("Product")

    assert [
        (definition.kind, definition.path)
        for definition in result.definitions
    ] == [("class", "app/models.py")]
    assert {
        (reference.reference_type, reference.path)
        for reference in result.references
    } >= {
        ("import", "app/repository.py"),
        ("import", "tests/test_models.py"),
    }
    assert result.related_tests == ["tests/test_models.py"]
    assert "Product" in result.related_classes
    assert "app/models.py" in result.related_files


def test_dependency_query_accepts_file_class_and_symbol(
    query_engine: KnowledgeQueryEngine,
) -> None:
    by_file = query_engine.dependencies("app/service.py")
    by_class = query_engine.dependencies("ProductRepository")
    by_symbol = query_engine.dependencies("load_product")

    assert by_file.dependencies == ["app/repository.py"]
    assert by_class.dependencies == ["app/models.py"]
    assert by_symbol.dependencies == ["app/repository.py"]


def test_reverse_dependency_query_returns_direct_dependents(
    query_engine: KnowledgeQueryEngine,
) -> None:
    result = query_engine.reverse_dependencies("app/models.py")

    assert result.dependents == [
        "app/repository.py",
        "tests/test_models.py",
    ]
    assert "app/service.py" not in result.dependents


def test_impact_analysis_returns_transitive_dependents_and_tests(
    query_engine: KnowledgeQueryEngine,
) -> None:
    result = query_engine.analyze_impact("Product")

    assert result.dependents == [
        "app/repository.py",
        "tests/test_models.py",
    ]
    assert result.impacted_files == [
        "app/cli.py",
        "app/repository.py",
        "app/service.py",
        "tests/test_models.py",
        "tests/test_service.py",
    ]
    assert result.related_tests == [
        "tests/test_models.py",
        "tests/test_service.py",
    ]
    assert {
        symbol.qualified_name
        for symbol in result.impacted_symbols
    } >= {
        "ProductRepository",
        "load_product",
        "main",
    }


def test_query_results_support_json_and_readable_summary(
    query_engine: KnowledgeQueryEngine,
) -> None:
    result = query_engine.find_symbol("Product")
    payload = result.to_dict()
    summary = result.to_summary()

    assert json.loads(result.to_json()) == payload
    assert payload["definitions"][0]["path"] == "app/models.py"
    assert "Symbol Query: Product" in summary
    assert "Definitions: 1" in summary
    assert "References:" in summary
    assert "class Product (app/models.py:1)" in summary


def test_unknown_and_blank_queries_are_explicit(
    query_engine: KnowledgeQueryEngine,
) -> None:
    unknown = query_engine.analyze_impact("MissingSymbol")

    assert unknown.target_files == []
    assert unknown.impacted_files == []
    assert "No related components found." in unknown.to_summary()

    with pytest.raises(ValueError, match="must not be blank"):
        query_engine.find_symbol(" ")


def test_duplicate_symbol_returns_every_definition_and_aggregates_impact(
    tmp_path: Path,
) -> None:
    build_duplicate_symbol_repository(tmp_path)
    query_engine = KnowledgeQueryEngine(
        ProjectScanner(tmp_path).scan()
    )

    symbol_result = query_engine.find_symbol("Shared")
    impact_result = query_engine.analyze_impact("Shared")

    assert [
        definition.path
        for definition in symbol_result.definitions
    ] == [
        "app/first.py",
        "app/second.py",
    ]
    assert impact_result.target_files == [
        "app/first.py",
        "app/second.py",
    ]
    assert impact_result.impacted_files == [
        "app/use_first.py",
        "app/use_second.py",
    ]


def test_circular_dependency_impact_terminates_without_readding_target(
    tmp_path: Path,
) -> None:
    build_circular_dependency_repository(tmp_path)
    query_engine = KnowledgeQueryEngine(
        ProjectScanner(tmp_path).scan()
    )

    result = query_engine.analyze_impact("app/a.py")

    assert result.target_files == ["app/a.py"]
    assert result.dependents == [
        "app/b.py",
        "app/consumer.py",
    ]
    assert result.impacted_files == [
        "app/b.py",
        "app/consumer.py",
    ]
    assert "app/a.py" not in result.impacted_files


def test_missing_file_queries_return_explicit_empty_results(
    query_engine: KnowledgeQueryEngine,
) -> None:
    missing_path = "app/does_not_exist.py"

    dependencies = query_engine.dependencies(missing_path)
    reverse_dependencies = query_engine.reverse_dependencies(
        missing_path
    )
    impact = query_engine.analyze_impact(missing_path)

    assert dependencies.target_files == []
    assert dependencies.dependencies == []
    assert reverse_dependencies.target_files == []
    assert reverse_dependencies.dependents == []
    assert impact.target_files == []
    assert impact.impacted_files == []
