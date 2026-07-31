from __future__ import annotations

from pathlib import Path

from .models import (
    CodeRelationship,
    DocumentationMapping,
    ImportGraph,
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
    * Python import graph
    * Code ↔ Test mapping
    * Code ↔ Documentation mapping
    * KnowledgeGraph generation
    """

    def __init__(self, project: ProjectModel):
        self.project = project

        self.graph = KnowledgeGraph()

        self._python_index = self._build_python_index()

    # ---------------------------------------------------------
    # Public API
    # ---------------------------------------------------------

    def build(self) -> KnowledgeGraph:
        """
        Build every relationship.

        Returns
        -------
        KnowledgeGraph
        """

        self._build_import_graph()

        self._build_test_mapping()

        self._build_document_mapping()

        self.project.set_knowledge_graph(self.graph)

        return self.graph

    # ---------------------------------------------------------
    # Python Index
    # ---------------------------------------------------------

    def _build_python_index(
        self,
    ) -> dict[str, PythonFile]:

        index: dict[str, PythonFile] = {}

        for python_file in self.project.python_files:

            module = python_file.module

            if module:
                index[module] = python_file

        return index

    # ---------------------------------------------------------
    # Import Graph
    # ---------------------------------------------------------

    def _build_import_graph(
        self,
    ) -> None:

        for python_file in self.project.python_files:

            self._connect_imports(python_file)

    def _connect_imports(
        self,
        source: PythonFile,
    ) -> None:

        for module in source.import_modules:

            target = self._resolve_module(module)

            if target is None:
                continue

            relationship = CodeRelationship(
                importer=source.path,
                imported=target.path,
                symbol=module,
                relationship="import",
            )

            self.graph.add_relationship(
                relationship
            )

    # ---------------------------------------------------------
    # Module Resolver
    # ---------------------------------------------------------

    def _resolve_module(
        self,
        module: str,
    ) -> PythonFile | None:

        if module in self._python_index:
            return self._python_index[module]

        for name, file in self._python_index.items():

            if name.endswith(module):
                return file

        return None


    # ---------------------------------------------------------
    # Test Mapping
    # ---------------------------------------------------------

    def _build_test_mapping(self) -> None:
        """
        Build Code <-> Test relationships.

        Matching priority

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

            # ---------------------------------------------
            # Exact
            # ---------------------------------------------

            if test_stem == f"test_{source_stem}":

                confidence = 1.00
                reason = "Exact pytest naming"

            elif test_stem == f"{source_stem}_test":

                confidence = 0.98
                reason = "Alternative pytest naming"

            # ---------------------------------------------
            # Partial
            # ---------------------------------------------

            elif source_stem in test_stem:

                confidence = 0.80
                reason = "Filename contains source module"

            # ---------------------------------------------
            # Class name match
            # ---------------------------------------------

            elif source.analysis:

                class_names = {
                    cls.name.lower()
                    for cls in source.analysis.classes
                }

                if any(
                    cls in test_stem
                    for cls in class_names
                ):
                    confidence = 0.75
                    reason = "Class name inferred"

            # ---------------------------------------------
            # Function name match
            # ---------------------------------------------

            if (
                confidence == 0
                and source.analysis
            ):

                function_names = {
                    fn.name.lower()
                    for fn in source.analysis.functions
                }

                if any(
                    fn in test_stem
                    for fn in function_names
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
    def _is_test_file(
        python_file: PythonFile,
    ) -> bool:

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

        1. Exact filename
        2. README inside same directory
        3. Parent directory README
        4. Domain name
        """

        for source in self.project.python_files:
            self._connect_documents(source)

    def _connect_documents(
        self,
        source: PythonFile,
    ) -> None:

        source_stem = source.path.stem.lower()

        for document in self.project.markdown_files:

            confidence = 0.0
            reason = ""

            doc_name = document.path.stem.lower()

            # ---------------------------------------------
            # Exact filename
            # ---------------------------------------------

            if doc_name == source_stem:

                confidence = 1.00
                reason = "Matching filename"

            # ---------------------------------------------
            # Same directory README
            # ---------------------------------------------

            elif (
                doc_name == "readme"
                and document.path.parent == source.path.parent
            ):

                confidence = 0.95
                reason = "Directory README"

            # ---------------------------------------------
            # Parent README
            # ---------------------------------------------

            elif (
                doc_name == "readme"
                and document.path.parent
                in source.path.parents
            ):

                confidence = 0.85
                reason = "Parent README"

            # ---------------------------------------------
            # Domain name
            # ---------------------------------------------

            elif any(
                part.lower() == doc_name
                for part in source.path.parts
            ):

                confidence = 0.75
                reason = "Directory / domain match"

            # ---------------------------------------------
            # Title contains filename
            # ---------------------------------------------

            elif (
                document.title
                and source_stem
                in document.title.lower()
            ):

                confidence = 0.70
                reason = "Document title match"

            # ---------------------------------------------
            # Heading contains filename
            # ---------------------------------------------

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

    def relationships(self) -> list[CodeRelationship]:
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

    def find_orphan_python_files(
        self,
    ) -> list[PythonFile]:
        """
        Import 관계가 없는 Python 파일 반환.
        """
        connected: set[Path] = set()

        for relationship in self.graph.import_graph.relationships:
            connected.add(relationship.importer)
            connected.add(relationship.imported)

        return [
            python_file
            for python_file in self.project.python_files
            if python_file.path not in connected
        ]

    def find_untested_python_files(
        self,
    ) -> list[PythonFile]:
        """
        TestMapping이 존재하지 않는 Python 파일 반환.
        """
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

    def find_undocumented_python_files(
        self,
    ) -> list[PythonFile]:
        """
        DocumentationMapping이 없는 Python 파일 반환.
        """
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
    """
    Build complete KnowledgeGraph and attach it to ProjectModel.
    """
    matcher = ProjectMatcher(project)
    return matcher.build()


def build_import_graph(
    project: ProjectModel,
) -> ImportGraph:
    """
    Build only the import graph.
    """
    matcher = ProjectMatcher(project)
    matcher._build_import_graph()
    return matcher.import_graph()


def analyze_project(
    project: ProjectModel,
) -> dict[str, object]:
    """
    High-level helper used by generators.
    """
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