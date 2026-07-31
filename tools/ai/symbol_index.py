from __future__ import annotations

from collections import defaultdict

from .models import PythonFile


class SymbolIndex:
    """
    Project-wide symbol index.

    Maps symbol names to the Python files that define them.

    This index is intentionally lightweight so it can be reused by
    dependency analysis, graph building, AI context generation,
    architecture reports and future symbol resolution.
    """

    def __init__(self) -> None:
        self._symbols: dict[str, list[PythonFile]] = defaultdict(list)

    def add_file(
        self,
        python_file: PythonFile,
    ) -> None:
        """
        Index every class/function exported by one Python file.
        """

        for class_ref in python_file.classes:
            self._symbols[class_ref.name].append(
                python_file
            )

        for function_ref in python_file.functions:
            self._symbols[function_ref.name].append(
                python_file
            )

    def find(
        self,
        symbol: str,
    ) -> list[PythonFile]:
        return list(
            self._symbols.get(symbol, [])
        )

    def contains(
        self,
        symbol: str,
    ) -> bool:
        return symbol in self._symbols

    def __len__(self) -> int:
        return len(self._symbols)

    def to_dict(self) -> dict[str, list[str]]:
        return {
            symbol: [
                file.module
                for file in files
            ]
            for symbol, files in sorted(
                self._symbols.items()
            )
        }