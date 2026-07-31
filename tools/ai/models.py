from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .parser import (
    ClassReference,
    FunctionReference,
    ImportReference,
    PythonAnalysis,
)


# ==========================================================
# Base File Models
# ==========================================================


@dataclass(slots=True)
class FileNode:
    path: Path
    extension: str
    size: int

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def stem(self) -> str:
        return self.path.stem

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "extension": self.extension,
            "size": self.size,
        }


# ==========================================================
# File Types
# ==========================================================


@dataclass(slots=True)
class PythonFile(FileNode):
    """
    Python source file.

    parser.py의 PythonAnalysis를
    Single Source of Truth로 사용한다.
    """

    analysis: PythonAnalysis | None = None

    @property
    def imports(self) -> list[ImportReference]:
        if self.analysis is None:
            return []
        return self.analysis.imports

    @property
    def classes(self) -> list[ClassReference]:
        if self.analysis is None:
            return []
        return self.analysis.classes

    @property
    def functions(self) -> list[FunctionReference]:
        if self.analysis is None:
            return []
        return self.analysis.functions

    @property
    def module(self) -> str:
        """
        Return the best-effort Python module name.

        Examples
        --------
        app/domain/change/models.py
            -> app.domain.change.models

        tests/unit/test_parser.py
            -> tests.unit.test_parser
        """

        path = self.path.with_suffix("")

        parts = list(path.parts)

        # Windows absolute path
        if len(parts) >= 2 and parts[0].endswith(":"):
            parts = parts[1:]

        # Repository root candidates
        for marker in (
            "app",
            "tests",
            "tools",
            "docs",
        ):
            if marker in parts:
                parts = parts[parts.index(marker):]
                break

        if parts and parts[-1] == "__init__":
            parts.pop()

        return ".".join(parts)

    @property
    def has_analysis(self) -> bool:
        return self.analysis is not None

    def set_analysis(self, analysis: PythonAnalysis) -> None:
        self.analysis = analysis

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()

        data.update(
            {
                "module": self.module,
                "imports": len(self.imports),
                "classes": len(self.classes),
                "functions": len(self.functions),
                "analyzed": self.analysis is not None,
            }
        )

        return data


@dataclass(slots=True)
class MarkdownFile(FileNode):
    title: str = ""
    headings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()

        data.update(
            {
                "title": self.title,
                "headings": self.headings,
            }
        )

        return data


@dataclass(slots=True)
class ConfigFile(FileNode):

    def to_dict(self) -> dict[str, Any]:
        return super().to_dict()


# ==========================================================
# Entry Points
# ==========================================================


@dataclass(slots=True)
class EntryPoint:
    path: Path
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "reason": self.reason,
        }


# ==========================================================
# Directory Structure
# ==========================================================


@dataclass(slots=True)
class DirectoryNode:
    path: Path

    files: list[Path] = field(default_factory=list)

    children: list["DirectoryNode"] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.path.name

    def add_child(self, child: "DirectoryNode") -> None:
        self.children.append(child)

    def add_file(self, file: Path) -> None:
        self.files.append(file)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "files": [str(f) for f in self.files],
            "children": [c.to_dict() for c in self.children],
        }


# ==========================================================
# Domain Models
# ==========================================================


@dataclass(slots=True)
class Domain:
    """
    논리적인 프로젝트 도메인

    Example
    -------
    app
    engine
    infrastructure
    tests
    docs
    tools
    """

    name: str

    files: list[Path] = field(default_factory=list)

    def add_file(self, path: Path) -> None:
        if path not in self.files:
            self.files.append(path)

    @property
    def total_files(self) -> int:
        return len(self.files)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "total_files": self.total_files,
            "files": [str(f) for f in self.files],
        }


# ==========================================================
# Knowledge Graph
# ==========================================================


@dataclass(slots=True)
class CodeRelationship:
    """
    두 Python 파일 사이의 관계

    importer ----imports----> imported
    """

    importer: Path

    imported: Path

    symbol: str = ""

    relationship: str = "import"

    def to_dict(self) -> dict[str, Any]:
        return {
            "importer": str(self.importer),
            "imported": str(self.imported),
            "symbol": self.symbol,
            "relationship": self.relationship,
        }


@dataclass(slots=True)
class TestMapping:
    """
    코드 ↔ 테스트 관계
    """

    source: Path

    test: Path

    confidence: float = 1.0

    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": str(self.source),
            "test": str(self.test),
            "confidence": self.confidence,
            "reason": self.reason,
        }


@dataclass(slots=True)
class DocumentationMapping:
    """
    코드 ↔ 문서 관계
    """

    source: Path

    document: Path

    confidence: float = 1.0

    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": str(self.source),
            "document": str(self.document),
            "confidence": self.confidence,
            "reason": self.reason,
        }


# ==========================================================
# Import Graph
# ==========================================================


@dataclass(slots=True)
class ImportGraph:

    relationships: list[CodeRelationship] = field(default_factory=list)

    def add(self, relationship: CodeRelationship) -> None:
        self.relationships.append(relationship)

    @property
    def total_relationships(self) -> int:
        return len(self.relationships)

    def imports_from(self, path: Path) -> list[CodeRelationship]:
        return [
            relationship
            for relationship in self.relationships
            if relationship.importer == path
        ]

    def imported_by(self, path: Path) -> list[CodeRelationship]:
        return [
            relationship
            for relationship in self.relationships
            if relationship.imported == path
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_relationships": self.total_relationships,
            "relationships": [
                relationship.to_dict()
                for relationship in self.relationships
            ],
        }


# ==========================================================
# Knowledge Graph Root
# ==========================================================


@dataclass(slots=True)
class KnowledgeGraph:

    import_graph: ImportGraph = field(default_factory=ImportGraph)

    test_mappings: list[TestMapping] = field(default_factory=list)

    documentation_mappings: list[DocumentationMapping] = field(
        default_factory=list
    )

    def add_relationship(
        self,
        relationship: CodeRelationship,
    ) -> None:
        self.import_graph.add(relationship)

    def add_test_mapping(
        self,
        mapping: TestMapping,
    ) -> None:
        self.test_mappings.append(mapping)

    def add_documentation_mapping(
        self,
        mapping: DocumentationMapping,
    ) -> None:
        self.documentation_mappings.append(mapping)

    @property
    def total_tests(self) -> int:
        return len(self.test_mappings)

    @property
    def total_documents(self) -> int:
        return len(self.documentation_mappings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "imports": self.import_graph.to_dict(),
            "tests": [
                mapping.to_dict()
                for mapping in self.test_mappings
            ],
            "documentation": [
                mapping.to_dict()
                for mapping in self.documentation_mappings
            ],
        }


# ==========================================================
# Project Model
# ==========================================================


@dataclass(slots=True)
class ProjectModel:
    root: Path

    directories: list[DirectoryNode] = field(default_factory=list)

    python_files: list[PythonFile] = field(default_factory=list)

    markdown_files: list[MarkdownFile] = field(default_factory=list)

    config_files: list[ConfigFile] = field(default_factory=list)

    entry_points: list[EntryPoint] = field(default_factory=list)

    domains: list[Domain] = field(default_factory=list)

    knowledge_graph: KnowledgeGraph | None = None

    # ------------------------------------------------------
    # Statistics
    # ------------------------------------------------------

    @property
    def total_python(self) -> int:
        return len(self.python_files)

    @property
    def total_markdown(self) -> int:
        return len(self.markdown_files)

    @property
    def total_config(self) -> int:
        return len(self.config_files)

    @property
    def total_entry_points(self) -> int:
        return len(self.entry_points)

    @property
    def total_directories(self) -> int:
        return len(self.directories)

    @property
    def total_domains(self) -> int:
        return len(self.domains)

    @property
    def total_files(self) -> int:
        return (
            self.total_python
            + self.total_markdown
            + self.total_config
        )

    # ------------------------------------------------------
    # Add Methods
    # ------------------------------------------------------

    def add_python(self, node: PythonFile) -> None:
        self.python_files.append(node)

    def add_markdown(self, node: MarkdownFile) -> None:
        self.markdown_files.append(node)

    def add_config(self, node: ConfigFile) -> None:
        self.config_files.append(node)

    def add_directory(self, node: DirectoryNode) -> None:
        self.directories.append(node)

    def add_entry_point(self, entry: EntryPoint) -> None:
        self.entry_points.append(entry)

    def add_domain(self, domain: Domain) -> None:
        self.domains.append(domain)

    def set_knowledge_graph(
        self,
        graph: KnowledgeGraph,
    ) -> None:
        self.knowledge_graph = graph

    # ------------------------------------------------------
    # Lookup
    # ------------------------------------------------------

    def find_python(
        self,
        path: Path,
    ) -> PythonFile | None:
        for node in self.python_files:
            if node.path == path:
                return node
        return None

    def find_markdown(
        self,
        path: Path,
    ) -> MarkdownFile | None:
        for node in self.markdown_files:
            if node.path == path:
                return node
        return None

    def find_config(
        self,
        path: Path,
    ) -> ConfigFile | None:
        for node in self.config_files:
            if node.path == path:
                return node
        return None

    def find_domain(
        self,
        name: str,
    ) -> Domain | None:
        for domain in self.domains:
            if domain.name == name:
                return domain
        return None

    # ------------------------------------------------------
    # Collections
    # ------------------------------------------------------

    def all_files(self) -> list[FileNode]:
        return [
            *self.python_files,
            *self.markdown_files,
            *self.config_files,
        ]

    def analyzed_python_files(self) -> list[PythonFile]:
        return [
            node
            for node in self.python_files
            if node.has_analysis
        ]

    def unanalyzed_python_files(self) -> list[PythonFile]:
        return [
            node
            for node in self.python_files
            if not node.has_analysis
        ]

    def entry_point_paths(self) -> list[Path]:
        return [entry.path for entry in self.entry_points]

    def domain_names(self) -> list[str]:
        return [domain.name for domain in self.domains]

    # ------------------------------------------------------
    # Summary
    # ------------------------------------------------------

    def summary(self) -> dict[str, int]:
        return {
            "python": self.total_python,
            "markdown": self.total_markdown,
            "config": self.total_config,
            "directories": self.total_directories,
            "entry_points": self.total_entry_points,
            "domains": self.total_domains,
            "files": self.total_files,
        }


    # ------------------------------------------------------
    # Iterators
    # ------------------------------------------------------

    def iter_python(self):
        yield from self.python_files

    def iter_markdown(self):
        yield from self.markdown_files

    def iter_config(self):
        yield from self.config_files

    def iter_domains(self):
        yield from self.domains

    def iter_directories(self):
        yield from self.directories

    # ------------------------------------------------------
    # Serialization
    # ------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "summary": self.summary(),
            "directories": [
                directory.to_dict()
                for directory in self.directories
            ],
            "python_files": [
                python_file.to_dict()
                for python_file in self.python_files
            ],
            "markdown_files": [
                markdown.to_dict()
                for markdown in self.markdown_files
            ],
            "config_files": [
                config.to_dict()
                for config in self.config_files
            ],
            "entry_points": [
                entry.to_dict()
                for entry in self.entry_points
            ],
            "domains": [
                domain.to_dict()
                for domain in self.domains
            ],
            "knowledge_graph": (
                self.knowledge_graph.to_dict()
                if self.knowledge_graph is not None
                else None
            ),
        }

    def to_json_dict(self) -> dict[str, Any]:
        """
        JSON 직렬화를 위한 Dictionary 반환.

        Path 객체를 문자열로 변환한 상태를 보장한다.
        """
        return self.to_dict()

    # ------------------------------------------------------
    # Magic Methods
    # ------------------------------------------------------

    def __len__(self) -> int:
        return self.total_files

    def __contains__(self, path: Path | str) -> bool:
        path = Path(path)

        return any(
            node.path == path
            for node in self.all_files()
        )

    def __repr__(self) -> str:
        return (
            "ProjectModel("
            f"root={self.root!s}, "
            f"python={self.total_python}, "
            f"markdown={self.total_markdown}, "
            f"config={self.total_config}, "
            f"domains={self.total_domains}, "
            f"entry_points={self.total_entry_points}"
            ")"
        )


# ==========================================================
# Helper Functions
# ==========================================================


def project_to_dict(project: ProjectModel) -> dict[str, Any]:
    """
    ProjectModel → dict
    """
    return project.to_dict()


def project_to_json(project: ProjectModel) -> dict[str, Any]:
    """
    JSON 출력용 Dictionary
    """
    return project.to_json_dict()