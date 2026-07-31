from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .matcher import ProjectMatcher
from .models import KnowledgeGraph, ProjectModel, PythonFile


@dataclass(frozen=True, slots=True)
class SymbolLocation:
    name: str
    qualified_name: str
    kind: str
    path: str
    line_number: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "qualified_name": self.qualified_name,
            "kind": self.kind,
            "path": self.path,
            "line_number": self.line_number,
        }


@dataclass(frozen=True, slots=True)
class SymbolReference:
    symbol: str
    path: str
    line_number: int
    reference_type: str
    context: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "path": self.path,
            "line_number": self.line_number,
            "reference_type": self.reference_type,
            "context": self.context,
        }


@dataclass(slots=True)
class KnowledgeQueryResult:
    query_type: str
    target: str
    target_files: list[str] = field(default_factory=list)
    definitions: list[SymbolLocation] = field(default_factory=list)
    references: list[SymbolReference] = field(default_factory=list)
    related_tests: list[str] = field(default_factory=list)
    related_classes: list[str] = field(default_factory=list)
    related_files: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    dependents: list[str] = field(default_factory=list)
    impacted_files: list[str] = field(default_factory=list)
    impacted_symbols: list[SymbolLocation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_type": self.query_type,
            "target": self.target,
            "target_files": list(self.target_files),
            "definitions": [
                definition.to_dict()
                for definition in self.definitions
            ],
            "references": [
                reference.to_dict()
                for reference in self.references
            ],
            "related_tests": list(self.related_tests),
            "related_classes": list(self.related_classes),
            "related_files": list(self.related_files),
            "dependencies": list(self.dependencies),
            "dependents": list(self.dependents),
            "impacted_files": list(self.impacted_files),
            "impacted_symbols": [
                symbol.to_dict()
                for symbol in self.impacted_symbols
            ],
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(
            self.to_dict(),
            indent=indent,
            ensure_ascii=False,
            sort_keys=True,
        )

    def to_summary(self) -> str:
        lines = [
            f"{self.query_type.replace('_', ' ').title()}: {self.target}",
            f"Target files: {len(self.target_files)}",
        ]

        if self.definitions:
            lines.append(f"Definitions: {len(self.definitions)}")
            lines.extend(
                "  - "
                f"{definition.kind} {definition.qualified_name} "
                f"({definition.path}:{definition.line_number})"
                for definition in self.definitions
            )

        if self.references:
            lines.append(f"References: {len(self.references)}")
            lines.extend(
                "  - "
                f"{reference.reference_type} "
                f"{reference.path}:{reference.line_number} "
                f"({reference.context})"
                for reference in self.references
            )

        path_sections = (
            ("Dependencies", self.dependencies),
            ("Dependents", self.dependents),
            ("Related tests", self.related_tests),
            ("Impacted files", self.impacted_files),
        )
        for label, values in path_sections:
            if values:
                lines.append(f"{label}: {len(values)}")
                lines.extend(
                    f"  - {value}"
                    for value in values
                )

        if not (
            self.definitions
            or self.references
            or any(values for _, values in path_sections)
        ):
            lines.append("No related components found.")

        return "\n".join(lines)


class KnowledgeQueryEngine:
    """
    Read-only queries over a scanned project and its knowledge graph.

    The engine reuses the existing AST analysis and file-level import
    graph. It does not add fields to AI_INDEX or project_map.
    """

    def __init__(
        self,
        project: ProjectModel,
        graph: KnowledgeGraph | None = None,
    ) -> None:
        self.project = project
        self.graph = graph or project.knowledge_graph

        if self.graph is None:
            self.graph = ProjectMatcher(project).build()

        self._files_by_path = {
            python_file.path: python_file
            for python_file in project.python_files
        }

    def find_symbol(self, name: str) -> KnowledgeQueryResult:
        target = self._validate_target(name)
        definitions = self._find_definitions(target)
        definition_paths = {
            self._absolute_path(definition.path)
            for definition in definitions
        }
        references = self._find_references(target)
        reference_paths = {
            self._absolute_path(reference.path)
            for reference in references
        }
        related_paths = definition_paths | reference_paths

        return KnowledgeQueryResult(
            query_type="symbol_query",
            target=target,
            target_files=self._relative_paths(definition_paths),
            definitions=definitions,
            references=references,
            related_tests=self._related_tests(related_paths),
            related_classes=self._classes_in_files(related_paths),
            related_files=self._relative_paths(related_paths),
        )

    def dependencies(
        self,
        target: str | Path,
    ) -> KnowledgeQueryResult:
        target_text = self._validate_target(target)
        target_files = self._resolve_target_files(target)
        dependency_paths = {
            relationship.imported
            for target_file in target_files
            for relationship in self.graph.import_graph.imports_from(
                target_file.path
            )
        }

        return KnowledgeQueryResult(
            query_type="dependency_query",
            target=target_text,
            target_files=self._paths_for_files(target_files),
            dependencies=self._relative_paths(dependency_paths),
            related_files=self._relative_paths(dependency_paths),
        )

    def reverse_dependencies(
        self,
        target: str | Path,
    ) -> KnowledgeQueryResult:
        target_text = self._validate_target(target)
        target_files = self._resolve_target_files(target)
        dependent_paths = {
            relationship.importer
            for target_file in target_files
            for relationship in self.graph.import_graph.imported_by(
                target_file.path
            )
        }

        return KnowledgeQueryResult(
            query_type="reverse_dependency_query",
            target=target_text,
            target_files=self._paths_for_files(target_files),
            dependents=self._relative_paths(dependent_paths),
            related_files=self._relative_paths(dependent_paths),
        )

    def analyze_impact(
        self,
        target: str | Path,
    ) -> KnowledgeQueryResult:
        target_text = self._validate_target(target)
        target_files = self._resolve_target_files(target)
        target_paths = {
            python_file.path
            for python_file in target_files
        }
        impacted_paths = self._transitive_dependents(target_paths)
        affected_paths = target_paths | impacted_paths

        return KnowledgeQueryResult(
            query_type="impact_analysis",
            target=target_text,
            target_files=self._paths_for_files(target_files),
            dependents=self._direct_dependents(target_paths),
            related_tests=self._related_tests(affected_paths),
            related_classes=self._classes_in_files(affected_paths),
            related_files=self._relative_paths(affected_paths),
            impacted_files=self._relative_paths(impacted_paths),
            impacted_symbols=self._definitions_in_files(
                impacted_paths
            ),
        )

    def _find_definitions(self, name: str) -> list[SymbolLocation]:
        definitions: list[SymbolLocation] = []

        for python_file in self.project.python_files:
            analysis = python_file.analysis
            if analysis is None:
                continue

            for class_reference in analysis.iter_classes():
                if self._symbol_matches(
                    name,
                    class_reference.name,
                    class_reference.qualified_name,
                ):
                    definitions.append(
                        SymbolLocation(
                            name=class_reference.name,
                            qualified_name=(
                                class_reference.qualified_name
                            ),
                            kind="class",
                            path=self._relative_path(
                                python_file.path
                            ),
                            line_number=class_reference.line_number,
                        )
                    )

            for function_reference in analysis.iter_functions():
                if self._symbol_matches(
                    name,
                    function_reference.name,
                    function_reference.qualified_name,
                ):
                    definitions.append(
                        SymbolLocation(
                            name=function_reference.name,
                            qualified_name=(
                                function_reference.qualified_name
                            ),
                            kind=(
                                "method"
                                if function_reference.is_method
                                else "function"
                            ),
                            path=self._relative_path(
                                python_file.path
                            ),
                            line_number=(
                                function_reference.line_number
                            ),
                        )
                    )

        return self._sorted_locations(definitions)

    def _find_references(self, name: str) -> list[SymbolReference]:
        references: list[SymbolReference] = []

        for python_file in self.project.python_files:
            analysis = python_file.analysis
            if analysis is None:
                continue

            for import_reference in analysis.imports:
                candidates = (
                    import_reference.names
                    or (import_reference.module,)
                )
                if any(
                    self._reference_matches(name, candidate)
                    for candidate in candidates
                ):
                    references.append(
                        SymbolReference(
                            symbol=name,
                            path=self._relative_path(
                                python_file.path
                            ),
                            line_number=(
                                import_reference.line_number
                            ),
                            reference_type="import",
                            context=(
                                import_reference.dotted_module
                            ),
                        )
                    )

            for function_reference in analysis.iter_functions():
                for call in function_reference.calls:
                    if not self._reference_matches(name, call):
                        continue
                    references.append(
                        SymbolReference(
                            symbol=name,
                            path=self._relative_path(
                                python_file.path
                            ),
                            line_number=(
                                function_reference.line_number
                            ),
                            reference_type="call",
                            context=(
                                function_reference.qualified_name
                            ),
                        )
                    )

        unique = {
            (
                reference.path,
                reference.line_number,
                reference.reference_type,
                reference.context,
            ): reference
            for reference in references
        }
        return [
            unique[key]
            for key in sorted(unique)
        ]

    def _resolve_target_files(
        self,
        target: str | Path,
    ) -> list[PythonFile]:
        target_text = str(target).strip()
        normalized = target_text.replace("\\", "/")
        matches: dict[Path, PythonFile] = {}

        for python_file in self.project.python_files:
            relative = self._relative_path(python_file.path)
            candidates = {
                str(python_file.path),
                python_file.path.as_posix(),
                relative,
                relative.replace("\\", "/"),
                python_file.path.name,
                python_file.module,
            }
            if target_text in candidates or normalized in candidates:
                matches[python_file.path] = python_file

        for definition in self._find_definitions(target_text):
            path = self._absolute_path(definition.path)
            python_file = self._files_by_path.get(path)
            if python_file is not None:
                matches[path] = python_file

        return [
            matches[path]
            for path in sorted(
                matches,
                key=lambda item: self._relative_path(item),
            )
        ]

    def _transitive_dependents(
        self,
        target_paths: set[Path],
    ) -> set[Path]:
        impacted: set[Path] = set()
        queue = deque(sorted(target_paths, key=str))

        while queue:
            current = queue.popleft()
            for relationship in self.graph.import_graph.imported_by(
                current
            ):
                dependent = relationship.importer
                if dependent in target_paths or dependent in impacted:
                    continue
                impacted.add(dependent)
                queue.append(dependent)

        return impacted

    def _direct_dependents(
        self,
        target_paths: set[Path],
    ) -> list[str]:
        paths = {
            relationship.importer
            for target_path in target_paths
            for relationship in self.graph.import_graph.imported_by(
                target_path
            )
        }
        return self._relative_paths(paths)

    def _related_tests(self, paths: set[Path]) -> list[str]:
        test_paths = {
            mapping.test
            for mapping in self.graph.test_mappings
            if mapping.source in paths
        }
        test_paths.update(
            path
            for path in paths
            if self._is_test_path(path)
        )
        return self._relative_paths(test_paths)

    def _classes_in_files(self, paths: set[Path]) -> list[str]:
        classes = {
            class_reference.qualified_name
            for path in paths
            for class_reference in self._iter_classes(path)
        }
        return sorted(classes)

    def _definitions_in_files(
        self,
        paths: set[Path],
    ) -> list[SymbolLocation]:
        definitions: list[SymbolLocation] = []

        for path in paths:
            python_file = self._files_by_path.get(path)
            if python_file is None or python_file.analysis is None:
                continue

            for class_reference in python_file.analysis.iter_classes():
                definitions.append(
                    SymbolLocation(
                        name=class_reference.name,
                        qualified_name=class_reference.qualified_name,
                        kind="class",
                        path=self._relative_path(path),
                        line_number=class_reference.line_number,
                    )
                )

            for function_reference in python_file.analysis.iter_functions():
                definitions.append(
                    SymbolLocation(
                        name=function_reference.name,
                        qualified_name=function_reference.qualified_name,
                        kind=(
                            "method"
                            if function_reference.is_method
                            else "function"
                        ),
                        path=self._relative_path(path),
                        line_number=function_reference.line_number,
                    )
                )

        return self._sorted_locations(definitions)

    def _iter_classes(self, path: Path):
        python_file = self._files_by_path.get(path)
        if python_file is None or python_file.analysis is None:
            return ()
        return python_file.analysis.iter_classes()

    def _paths_for_files(
        self,
        python_files: list[PythonFile],
    ) -> list[str]:
        return self._relative_paths(
            {
                python_file.path
                for python_file in python_files
            }
        )

    def _relative_paths(self, paths: set[Path]) -> list[str]:
        return sorted(
            {
                self._relative_path(path)
                for path in paths
            }
        )

    def _relative_path(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(
                self.project.root
            ).as_posix()
        except ValueError:
            return path.as_posix()

    def _absolute_path(self, path: str) -> Path:
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate.resolve()
        return (self.project.root / candidate).resolve()

    @staticmethod
    def _validate_target(target: str | Path) -> str:
        target_text = str(target).strip()
        if not target_text:
            raise ValueError("query target must not be blank")
        return target_text

    @staticmethod
    def _symbol_matches(
        query: str,
        name: str,
        qualified_name: str,
    ) -> bool:
        return query in {name, qualified_name}

    @staticmethod
    def _reference_matches(query: str, candidate: str) -> bool:
        return (
            candidate == query
            or candidate.endswith(f".{query}")
            or query.endswith(f".{candidate}")
        )

    @staticmethod
    def _is_test_path(path: Path) -> bool:
        return (
            path.stem.startswith("test_")
            or "tests" in {
                part.lower()
                for part in path.parts
            }
        )

    @staticmethod
    def _sorted_locations(
        locations: list[SymbolLocation],
    ) -> list[SymbolLocation]:
        return sorted(
            locations,
            key=lambda item: (
                item.path,
                item.line_number,
                item.qualified_name,
            ),
        )
