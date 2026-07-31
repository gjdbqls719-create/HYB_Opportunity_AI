from __future__ import annotations

import json
from pathlib import Path

from tools.ai.build_ai_index import build_project_map
from tools.ai.graph_builder import GraphBuilder
from tools.ai.matcher import ProjectMatcher
from tools.ai.scanner import ProjectScanner


def build_sample_repository(root: Path) -> None:
    app_directory = root / "app"
    tests_directory = root / "tests"
    docs_directory = root / "docs"

    app_directory.mkdir()
    tests_directory.mkdir()
    docs_directory.mkdir()

    (app_directory / "__init__.py").write_text(
        "",
        encoding="utf-8",
    )
    (app_directory / "catalog.py").write_text(
        "class Catalog:\n"
        "    def find(self) -> str:\n"
        "        return 'item'\n\n"
        "def create_catalog() -> Catalog:\n"
        "    return Catalog()\n",
        encoding="utf-8",
    )
    (app_directory / "service.py").write_text(
        "from app.catalog import Catalog\n\n"
        "def build_catalog() -> Catalog:\n"
        "    return Catalog()\n",
        encoding="utf-8",
    )
    (app_directory / "README.md").write_text(
        "# App\n",
        encoding="utf-8",
    )
    (tests_directory / "test_catalog.py").write_text(
        "from app.catalog import Catalog\n\n"
        "def test_catalog() -> None:\n"
        "    assert Catalog().find() == 'item'\n",
        encoding="utf-8",
    )
    (docs_directory / "catalog.md").write_text(
        "# Catalog\n",
        encoding="utf-8",
    )


def test_project_scanner_builds_python_analysis(tmp_path: Path) -> None:
    build_sample_repository(tmp_path)

    project = ProjectScanner(tmp_path).scan()
    catalog = next(
        file
        for file in project.python_files
        if file.path.name == "catalog.py"
    )

    assert project.total_python == 4
    assert project.total_markdown == 2
    assert catalog.module == "app.catalog"
    assert [class_reference.name for class_reference in catalog.classes] == [
        "Catalog"
    ]
    assert [
        function_reference.name
        for function_reference in catalog.functions
    ] == ["create_catalog"]
    assert catalog.analysis is not None
    assert catalog.analysis.function_names == (
        "create_catalog",
        "Catalog.find",
    )


def test_project_matcher_builds_repository_relationships(
    tmp_path: Path,
) -> None:
    build_sample_repository(tmp_path)
    project = ProjectScanner(tmp_path).scan()

    graph = ProjectMatcher(project).build()

    relationships = {
        (
            relationship.importer.name,
            relationship.imported.name,
        )
        for relationship in graph.import_graph.relationships
    }
    test_mappings = {
        (mapping.source.name, mapping.test.name)
        for mapping in graph.test_mappings
    }
    documentation_mappings = {
        (mapping.source.name, mapping.document.name)
        for mapping in graph.documentation_mappings
    }

    assert ("service.py", "catalog.py") in relationships
    assert ("catalog.py", "test_catalog.py") in test_mappings
    assert ("catalog.py", "catalog.md") in documentation_mappings
    assert project.knowledge_graph is graph


def test_graph_builder_builds_and_exports_graph(
    tmp_path: Path,
) -> None:
    build_sample_repository(tmp_path)
    project = ProjectScanner(tmp_path).scan()

    builder = GraphBuilder(project)
    result = builder.build()
    exported = builder.export_ai_context()

    assert result.project is project
    assert result.graph.import_graph.relationships
    assert project.knowledge_graph is not None
    assert result.statistics["python_files"] == 4
    assert result.statistics["relationships"] >= 2
    assert exported["statistics"]["python_files"] == 4
    assert exported["knowledge_graph"]["imports"]["relationships"]


def test_build_project_map_preserves_serializable_name_lists(
    tmp_path: Path,
) -> None:
    build_sample_repository(tmp_path)
    project = ProjectScanner(tmp_path).scan()

    project_map = build_project_map(project)
    serialized = json.dumps(project_map)
    catalog = next(
        file
        for file in project_map["python_files"]
        if file["path"] == str(Path("app") / "catalog.py")
    )

    assert serialized
    assert catalog["classes"] == ["Catalog"]
    assert catalog["functions"] == ["create_catalog", "find"]
