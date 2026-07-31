from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .matcher import ProjectMatcher
from .models import (
    ImportGraph,
    KnowledgeGraph,
    ProjectModel,
)


@dataclass(slots=True)
class GraphBuildResult:
    """
    Result returned after building the repository knowledge graph.
    """

    project: ProjectModel
    graph: KnowledgeGraph
    statistics: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "statistics": self.statistics,
            "graph": self.graph.to_dict(),
        }


class GraphBuilder:
    """
    High-level builder used by AI generators.

    Repository
        ↓
    ProjectModel
        ↓
    ProjectMatcher
        ↓
    KnowledgeGraph
        ↓
    JSON Generators
    """

    def __init__(self, project: ProjectModel):
        self.project = project

    def build(self) -> GraphBuildResult:

        matcher = ProjectMatcher(self.project)

        graph = matcher.build()

        return GraphBuildResult(
            project=self.project,
            graph=graph,
            statistics=matcher.graph_statistics(),
        )

    # ---------------------------------------------------------
    # Export Helpers
    # ---------------------------------------------------------

    def export_import_graph(self) -> dict[str, Any]:
        """
        Export import graph.
        """

        result = self.build()

        graph: ImportGraph = result.graph.import_graph

        return {
            "relationship_count": len(graph.relationships),
            "relationships": [
                relationship.to_dict()
                for relationship in graph.relationships
            ],
        }

    def export_test_map(self) -> dict[str, Any]:
        """
        Export Code <-> Test mappings.
        """

        result = self.build()

        return {
            "mapping_count": len(result.graph.test_mappings),
            "mappings": [
                mapping.to_dict()
                for mapping in result.graph.test_mappings
            ],
        }

    def export_doc_map(self) -> dict[str, Any]:
        """
        Export Code <-> Documentation mappings.
        """

        result = self.build()

        return {
            "mapping_count": len(result.graph.documentation_mappings),
            "mappings": [
                mapping.to_dict()
                for mapping in result.graph.documentation_mappings
            ],
        }

    def export_ai_context(self) -> dict[str, Any]:
        """
        Export complete AI context.
        """

        result = self.build()

        return {
            "statistics": result.statistics,
            "knowledge_graph": result.graph.to_dict(),
            "python_files": [
                file.to_dict()
                for file in self.project.python_files
            ],
            "markdown_files": [
                file.to_dict()
                for file in self.project.markdown_files
            ],
            "config_files": [
                file.to_dict()
                for file in self.project.config_files
            ],
            "entry_points": [
                entry.to_dict()
                for entry in self.project.entry_points
            ],
        }

    # ---------------------------------------------------------
    # Save Helpers
    # ---------------------------------------------------------

    @staticmethod
    def _write_json(
        output_path: Path,
        data: dict[str, Any],
    ) -> Path:
        """
        Write JSON with stable formatting.
        """

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        output_path.write_text(
            json.dumps(
                data,
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        return output_path

    # ---------------------------------------------------------
    # Public Save API
    # ---------------------------------------------------------

    def save_import_graph(
        self,
        output_path: Path,
    ) -> Path:

        return self._write_json(
            output_path,
            self.export_import_graph(),
        )

    def save_test_map(
        self,
        output_path: Path,
    ) -> Path:

        return self._write_json(
            output_path,
            self.export_test_map(),
        )

    def save_doc_map(
        self,
        output_path: Path,
    ) -> Path:

        return self._write_json(
            output_path,
            self.export_doc_map(),
        )

    def save_ai_context(
        self,
        output_path: Path,
    ) -> Path:

        return self._write_json(
            output_path,
            self.export_ai_context(),
        )

# ---------------------------------------------------------
# Convenience API
# ---------------------------------------------------------


def build_graph(
    project: ProjectModel,
) -> GraphBuildResult:
    """
    Build the complete repository knowledge graph.
    """

    return GraphBuilder(project).build()


def export_all(
    project: ProjectModel,
    output_directory: Path,
) -> dict[str, Path]:
    """
    Export every graph artifact.
    """

    builder = GraphBuilder(project)

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    outputs = {
        "ai_context": builder.save_ai_context(
            output_directory / "AI_CONTEXT.json"
        ),
        "import_graph": builder.save_import_graph(
            output_directory / "IMPORT_GRAPH.json"
        ),
        "test_map": builder.save_test_map(
            output_directory / "TEST_MAP.json"
        ),
        "doc_map": builder.save_doc_map(
            output_directory / "DOC_MAP.json"
        ),
    }

    return outputs


def build_statistics(
    project: ProjectModel,
) -> dict[str, int]:
    """
    Return repository statistics.
    """

    return (
        GraphBuilder(project)
        .build()
        .statistics
    )


def export_summary(
    project: ProjectModel,
) -> dict[str, Any]:
    """
    Small summary used by CLI output.
    """

    result = GraphBuilder(project).build()

    return {
        "statistics": result.statistics,
        "python_files": len(project.python_files),
        "markdown_files": len(project.markdown_files),
        "config_files": len(project.config_files),
        "entry_points": len(project.entry_points),
        "relationships": len(
            result.graph.import_graph.relationships
        ),
        "test_mappings": len(
            result.graph.test_mappings
        ),
        "documentation_mappings": len(
            result.graph.documentation_mappings
        ),
    }
