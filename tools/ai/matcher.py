from __future__ import annotations

from pathlib import Path

from .import_graph_builder import ImportGraphBuilder
from .models import (
    DocumentationMapping,
    ImportGraph,
    ImportReference,
    KnowledgeGraph,
    ProjectModel,
    PythonFile,
    TestMapping,
)


class ProjectMatcher:
    """
    Build relationships inside a ProjectModel.

    Responsibilities
    ----------------
    * Import-graph orchestration
    * Code ↔ Test mapping
    * Code ↔ Documentation mapping
    * KnowledgeGraph generation
    """

    def __init__(self, project: ProjectModel):
        self.project = project
        self.graph = KnowledgeGraph()
        self._import_graph_builder = ImportGraphBuilder(
            project=self.project,
            graph=self.graph,
        )

    # ---------------------------------------------------------
    # Public API
    # ---------------------------------------------------------

    def build(self) -> KnowledgeGraph:
        """Build every relationship and attach the graph to the project."""
        self._build_import_graph()
        self._build_test_mapping()
        self._build_document_mapping()

        self.project.set_knowledge_graph(self.graph)

        return self.graph

    # ---------------------------------------------------------
    # Import Graph
    # ---------------------------------------------------------

    def _build_import_graph(self) -> None:
        self._import_graph_builder.build()

    # Compatibility delegates for existing callers and tests.

    def _resolve_module(self, module: str) -> PythonFile | None:
        return self._import_graph_builder.resolve_module(module)

    def _resolve_symbol(self, symbol: str) -> PythonFile | None:
        return self._import_graph_builder.resolve_symbol(symbol)

    def _resolve_relative_module(
        self,
        source: PythonFile,
        import_ref: ImportReference,
    ) -> str | None:
        return self._import_graph_builder.resolve_relative_module(
            source,
            import_ref,
        )

    # ---------------------------------------------------------
    # Test Mapping
    # ---------------------------------------------------------

    def _build_test_mapping(self) -> None:
        """
        Build Code <-> Test relationships.

        Matching priority
        -----------------
        1. Exact filename
        2. test_<name>.py
        3. <name>_test.py
        4. Stem contains source stem
        """
        test_files = [
            file
            for file in self.project.python_files
            if self._is_test_file(file)
        ]

        for source in self.project.python_files:
            if self._is_test_file(source):
                continue

            self._connect_tests(
                source,
                test_files,
            )

    def _connect_tests(
        self,
        source: PythonFile,
        test_files: list[PythonFile],
    ) -> None:
        source_stem = source.path.stem.lower()

        for test in test_files:
            confidence = 0.0
            reason = ""
            test_stem = test.path.stem.lower()

            if test_stem == f"test_{source_stem}":
                confidence = 1.00
                reason = "Exact pytest naming"

            elif test_stem == f"{source_stem}_test":
                confidence = 0.98
                reason = "Alternative pytest naming"

            elif source_stem in test_stem:
                confidence = 0.80
                reason = "Filename contains source module"

            elif source.analysis:
                class_names = {
                    cls.name.lower()
                    for cls in source.analysis.classes
                }

                if any(
                    class_name in test_stem
                    for class_name in class_names
                ):
                    confidence = 0.75
                    reason = "Class name inferred"

            if confidence == 0 and source.analysis:
                function_names = {
                    function.name.lower()
                    for function in source.analysis.functions
                }

                if any(
                    function_name in test_stem
                    for function_name in function_names
                ):
                    confidence = 0.65
                    reason = "Function name inferred"

            if confidence == 0:
                continue

            self.graph.add_test_mapping(
                TestMapping(
                    source=source.path,
                    test=test.path,
                    confidence=confidence,
                    reason=reason,
                )
            )

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------

    @staticmethod
    def _is_test_file(python_file: PythonFile) -> bool:
        stem = python_file.path.stem.lower()

        if stem.startswith("test_"):
            return True

        if stem.endswith("_test"):
            return True

        parts = {
            part.lower()
            for part in python_file.path.parts
        }

        return "tests" in parts

    # ---------------------------------------------------------
    # Documentation Mapping
    # ---------------------------------------------------------

    def _build_document_mapping(self) -> None:
        """
        Build relationships between Python modules and Markdown
        documentation.

        Matching priority
        -----------------
        1. Exact filename
        2. README inside same directory
        3. Parent directory README
        4. Domain name
        """
        for source in self.project.python_files:
            self._connect_documents(source)

    def _connect_documents(self, source: PythonFile) -> None:
        source_stem = source.path.stem.lower()

        for document in self.project.markdown_files:
            confidence = 0.0
            reason = ""
            doc_name = document.path.stem.lower()

            if doc_name == source_stem:
                confidence = 1.00
                reason = "Matching filename"

            elif (
                doc_name == "readme"
                and document.path.parent == source.path.parent
            ):
                confidence = 0.95
                reason = "Directory README"

            elif (
                doc_name == "readme"
                and document.path.parent in source.path.parents
            ):
                confidence = 0.85
                reason = "Parent README"

            elif any(
                part.lower() == doc_name
                for part in source.path.parts
            ):
                confidence = 0.75
                reason = "Directory / domain match"

            elif (
                document.title
                and source_stem in document.title.lower()
            ):
                confidence = 0.70
                reason = "Document title match"

            elif any(
                source_stem in heading.lower()
                for heading in document.headings
            ):
                confidence = 0.65
                reason = "Document heading match"

            if confidence == 0:
                continue

            self.graph.add_documentation_mapping(
                DocumentationMapping(
                    source=source.path,
                    document=document.path,
                    confidence=confidence,
                    reason=reason,
                )
            )

    # ---------------------------------------------------------
    # Query API
    # ---------------------------------------------------------

    def import_graph(self) -> ImportGraph:
        return self.graph.import_graph

    def knowledge_graph(self) -> KnowledgeGraph:
        return self.graph

    def relationships(self):
        return self.graph.import_graph.relationships

    def test_mappings(self) -> list[TestMapping]:
        return self.graph.test_mappings

    def documentation_mappings(
        self,
    ) -> list[DocumentationMapping]:
        return self.graph.documentation_mappings

    # ---------------------------------------------------------
    # Analysis Helpers
    # ---------------------------------------------------------

    def find_orphan_python_files(self) -> list[PythonFile]:
        """Return Python files with no import relationship."""
        connected: set[Path] = set()

        for relationship in self.graph.import_graph.relationships:
            connected.add(relationship.importer)
            connected.add(relationship.imported)

        return [
            python_file
            for python_file in self.project.python_files
            if python_file.path not in connected
        ]

    def find_untested_python_files(self) -> list[PythonFile]:
        """Return non-test Python files without a TestMapping."""
        mapped = {
            mapping.source
            for mapping in self.graph.test_mappings
        }

        return [
            python_file
            for python_file in self.project.python_files
            if (
                not self._is_test_file(python_file)
                and python_file.path not in mapped
            )
        ]

    def find_undocumented_python_files(self) -> list[PythonFile]:
        """Return Python files without a DocumentationMapping."""
        mapped = {
            mapping.source
            for mapping in self.graph.documentation_mappings
        }

        return [
            python_file
            for python_file in self.project.python_files
            if python_file.path not in mapped
        ]

    # ---------------------------------------------------------
    # Statistics
    # ---------------------------------------------------------

    def graph_statistics(self) -> dict[str, int]:
        return {
            "python_files": self.project.total_python,
            "relationships": len(
                self.graph.import_graph.relationships
            ),
            "test_mappings": len(
                self.graph.test_mappings
            ),
            "documentation_mappings": len(
                self.graph.documentation_mappings
            ),
            "orphans": len(
                self.find_orphan_python_files()
            ),
            "untested": len(
                self.find_untested_python_files()
            ),
            "undocumented": len(
                self.find_undocumented_python_files()
            ),
        }


# ---------------------------------------------------------
# Convenience Functions
# ---------------------------------------------------------


def build_knowledge_graph(
    project: ProjectModel,
) -> KnowledgeGraph:
    """Build and attach a complete KnowledgeGraph."""
    return ProjectMatcher(project).build()


def build_import_graph(
    project: ProjectModel,
) -> ImportGraph:
    """Build only the import graph."""
    matcher = ProjectMatcher(project)
    matcher._build_import_graph()
    return matcher.import_graph()


def analyze_project(
    project: ProjectModel,
) -> dict[str, object]:
    """Return a high-level project relationship analysis."""
    matcher = ProjectMatcher(project)
    matcher.build()

    return {
        "statistics": matcher.graph_statistics(),
        "knowledge_graph": matcher.knowledge_graph().to_dict(),
        "orphans": [
            item.path.as_posix()
            for item in matcher.find_orphan_python_files()
        ],
        "untested": [
            item.path.as_posix()
            for item in matcher.find_untested_python_files()
        ],
        "undocumented": [
            item.path.as_posix()
            for item in matcher.find_undocumented_python_files()
        ],
    }
