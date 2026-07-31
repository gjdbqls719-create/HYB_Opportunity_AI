from __future__ import annotations

from .models import (
    CodeRelationship,
    ImportReference,
    KnowledgeGraph,
    ProjectModel,
    PythonFile,
)
from .symbol_index import SymbolIndex


class ImportGraphBuilder:
    """
    Build Python import relationships for a scanned project.

    Responsibilities
    ----------------
    * Python module index construction
    * Absolute and relative module resolution
    * Symbol-based fallback resolution
    * Import relationship creation
    """

    def __init__(
        self,
        project: ProjectModel,
        graph: KnowledgeGraph,
    ) -> None:
        self.project = project
        self.graph = graph

        self._python_index = self._build_python_index()
        self._symbol_index = SymbolIndex()

        for python_file in self.project.python_files:
            self._symbol_index.add_file(python_file)

    def build(self) -> None:
        """Build every Python import relationship."""
        for python_file in self.project.python_files:
            self._connect_imports(python_file)

    def _build_python_index(self) -> dict[str, PythonFile]:
        index: dict[str, PythonFile] = {}

        for python_file in self.project.python_files:
            module = python_file.module

            if module:
                index[module] = python_file

        return index

    def _connect_imports(self, source: PythonFile) -> None:
        for import_ref in source.imports:
            module = self.resolve_relative_module(
                source,
                import_ref,
            )

            if module is None:
                continue

            module = module.strip()

            if not module:
                continue

            target = self.resolve_module(module)

            if target is None:
                for name in import_ref.names:
                    candidate = f"{module}.{name}"
                    target = self.resolve_module(candidate)

                    if target is not None:
                        break

                    target = self.resolve_symbol(name)

                    if target is not None:
                        break

            if target is None:
                continue

            self.graph.add_relationship(
                CodeRelationship(
                    importer=source.path,
                    imported=target.path,
                    symbol=import_ref.dotted_module,
                    relationship="import",
                )
            )

    def resolve_module(self, module: str) -> PythonFile | None:
        """
        Resolve an imported module to a scanned Python file.

        Resolution order
        ----------------
        1. Exact module match
        2. Package ``__init__`` match
        3. Unique suffix match
        """
        module = module.strip()

        if not module:
            return None

        target = self._python_index.get(module)

        if target is not None:
            return target

        package_name = f"{module}.__init__"
        target = self._python_index.get(package_name)

        if target is not None:
            return target

        candidates = [
            python_file
            for name, python_file in self._python_index.items()
            if name.endswith(module)
        ]

        if len(candidates) == 1:
            return candidates[0]

        return None

    def resolve_symbol(self, symbol: str) -> PythonFile | None:
        """Resolve a symbol when exactly one project file defines it."""
        matches = self._symbol_index.find(symbol)

        if len(matches) == 1:
            return matches[0]

        return None

    @staticmethod
    def resolve_relative_module(
        source: PythonFile,
        import_ref: ImportReference,
    ) -> str | None:
        """
        Resolve a relative import into an absolute module name.

        Examples
        --------
        ``from .models import ChangeSet`` resolves against the source
        package, while ``from ..storage import repository`` moves one
        package level upward before appending ``storage``.
        """
        if not import_ref.is_relative:
            return import_ref.module

        parts = source.module.split(".")

        if not parts:
            return None

        remove_count = max(import_ref.level - 1, 0)

        if remove_count:
            if remove_count >= len(parts):
                return None

            parts = parts[:-remove_count]

        if import_ref.module:
            parts.extend(import_ref.module.split("."))

        return ".".join(parts)
