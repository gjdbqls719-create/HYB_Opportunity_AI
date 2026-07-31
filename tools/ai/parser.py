from __future__ import annotations

import ast
import tokenize
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Sequence


@dataclass(frozen=True, slots=True)
class ImportReference:
    """
    Python import statement extracted from an AST.

    Examples:
        import json
        import pathlib as paths
        from app.domain.change import ChangeSet
        from .models import ProjectModel
    """

    module: str
    names: tuple[str, ...] = ()
    aliases: tuple[tuple[str, str | None], ...] = ()
    level: int = 0
    line_number: int = 0

    @property
    def is_relative(self) -> bool:
        return self.level > 0

    @property
    def dotted_module(self) -> str:
        prefix = "." * self.level
        return f"{prefix}{self.module}" if self.module else prefix

    def to_dict(self) -> dict[str, object]:
        return {
            "module": self.module,
            "dotted_module": self.dotted_module,
            "names": list(self.names),
            "aliases": [
                {
                    "name": name,
                    "alias": alias,
                }
                for name, alias in self.aliases
            ],
            "level": self.level,
            "is_relative": self.is_relative,
            "line_number": self.line_number,
        }


@dataclass(frozen=True, slots=True)
class DecoratorReference:
    """
    Decorator attached to a class or function.
    """

    name: str
    expression: str
    line_number: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "expression": self.expression,
            "line_number": self.line_number,
        }


@dataclass(frozen=True, slots=True)
class ArgumentInfo:
    """
    Function or method argument metadata.
    """

    name: str
    kind: str
    annotation: str | None = None
    default: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "kind": self.kind,
            "annotation": self.annotation,
            "default": self.default,
        }


@dataclass(frozen=True, slots=True)
class FunctionReference:
    """
    Top-level function or class method discovered in a Python source file.
    """

    name: str
    qualified_name: str
    line_number: int
    end_line_number: int | None
    is_async: bool
    is_method: bool
    is_property: bool
    visibility: str
    arguments: tuple[ArgumentInfo, ...] = ()
    returns: str | None = None
    decorators: tuple[DecoratorReference, ...] = ()
    docstring: str | None = None
    raises: tuple[str, ...] = ()
    calls: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "qualified_name": self.qualified_name,
            "line_number": self.line_number,
            "end_line_number": self.end_line_number,
            "is_async": self.is_async,
            "is_method": self.is_method,
            "is_property": self.is_property,
            "visibility": self.visibility,
            "arguments": [
                argument.to_dict()
                for argument in self.arguments
            ],
            "returns": self.returns,
            "decorators": [
                decorator.to_dict()
                for decorator in self.decorators
            ],
            "docstring": self.docstring,
            "raises": list(self.raises),
            "calls": list(self.calls),
        }


@dataclass(frozen=True, slots=True)
class ClassReference:
    """
    Class metadata extracted from a Python source file.
    """

    name: str
    qualified_name: str
    line_number: int
    end_line_number: int | None
    visibility: str
    bases: tuple[str, ...] = ()
    decorators: tuple[DecoratorReference, ...] = ()
    docstring: str | None = None
    methods: tuple[FunctionReference, ...] = ()
    nested_classes: tuple["ClassReference", ...] = ()
    class_attributes: tuple[str, ...] = ()
    is_dataclass: bool = False
    is_enum: bool = False
    is_protocol: bool = False
    is_abstract: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "qualified_name": self.qualified_name,
            "line_number": self.line_number,
            "end_line_number": self.end_line_number,
            "visibility": self.visibility,
            "bases": list(self.bases),
            "decorators": [
                decorator.to_dict()
                for decorator in self.decorators
            ],
            "docstring": self.docstring,
            "methods": [
                method.to_dict()
                for method in self.methods
            ],
            "nested_classes": [
                nested_class.to_dict()
                for nested_class in self.nested_classes
            ],
            "class_attributes": list(self.class_attributes),
            "is_dataclass": self.is_dataclass,
            "is_enum": self.is_enum,
            "is_protocol": self.is_protocol,
            "is_abstract": self.is_abstract,
        }


@dataclass(frozen=True, slots=True)
class ParseIssue:
    """
    Non-fatal issue encountered while parsing a source file.
    """

    category: str
    message: str
    line_number: int | None = None
    column_offset: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "category": self.category,
            "message": self.message,
            "line_number": self.line_number,
            "column_offset": self.column_offset,
        }


@dataclass(slots=True)
class PythonAnalysis:
    """
    Complete lightweight analysis of one Python source file.

    This object is intentionally independent from ProjectModel so the parser
    can be tested and reused by scanners, graph builders, context generators,
    dependency analyzers, and architecture-audit tools.
    """

    path: Path
    encoding: str = "utf-8"
    module_docstring: str | None = None
    imports: list[ImportReference] = field(default_factory=list)
    functions: list[FunctionReference] = field(default_factory=list)
    classes: list[ClassReference] = field(default_factory=list)
    module_attributes: list[str] = field(default_factory=list)
    exported_names: list[str] = field(default_factory=list)
    issues: list[ParseIssue] = field(default_factory=list)
    source_size: int = 0
    line_count: int = 0

    @property
    def import_modules(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    item.dotted_module
                    for item in self.imports
                    if item.dotted_module
                }
            )
        )

    @property
    def function_names(self) -> tuple[str, ...]:
        return tuple(
            function.qualified_name
            for function in self.iter_functions()
        )

    @property
    def class_names(self) -> tuple[str, ...]:
        return tuple(
            class_reference.qualified_name
            for class_reference in self.iter_classes()
        )

    @property
    def has_errors(self) -> bool:
        return any(
            issue.category in {"syntax_error", "read_error"}
            for issue in self.issues
        )

    def iter_classes(self) -> Iterator[ClassReference]:
        for class_reference in self.classes:
            yield class_reference
            yield from self._iter_nested_classes(
                class_reference.nested_classes
            )

    def iter_functions(self) -> Iterator[FunctionReference]:
        yield from self.functions

        for class_reference in self.iter_classes():
            yield from class_reference.methods

    def to_dict(
        self,
        *,
        root: Path | None = None,
    ) -> dict[str, object]:
        output_path: str

        if root is not None:
            try:
                output_path = self.path.resolve().relative_to(
                    root.resolve()
                ).as_posix()
            except ValueError:
                output_path = self.path.as_posix()
        else:
            output_path = self.path.as_posix()

        return {
            "path": output_path,
            "encoding": self.encoding,
            "source_size": self.source_size,
            "line_count": self.line_count,
            "module_docstring": self.module_docstring,
            "imports": [
                item.to_dict()
                for item in self.imports
            ],
            "import_modules": list(self.import_modules),
            "functions": [
                function.to_dict()
                for function in self.functions
            ],
            "classes": [
                class_reference.to_dict()
                for class_reference in self.classes
            ],
            "module_attributes": list(self.module_attributes),
            "exported_names": list(self.exported_names),
            "issues": [
                issue.to_dict()
                for issue in self.issues
            ],
        }

    @staticmethod
    def _iter_nested_classes(
        classes: Sequence[ClassReference],
    ) -> Iterator[ClassReference]:
        for class_reference in classes:
            yield class_reference
            yield from PythonAnalysis._iter_nested_classes(
                class_reference.nested_classes
            )


class PythonSourceParser:
    """
    Parse Python files through the standard-library AST.

    Design goals:
        - no project imports are executed
        - syntax failures do not stop repository scanning
        - output is deterministic
        - parsing remains lightweight enough for full-repository use
        - extracted metadata can feed a future knowledge graph
    """

    def parse_file(self, path: Path) -> PythonAnalysis:
        resolved_path = path.resolve()

        if not resolved_path.exists():
            return PythonAnalysis(
                path=resolved_path,
                issues=[
                    ParseIssue(
                        category="read_error",
                        message="Python source file does not exist.",
                    )
                ],
            )

        if not resolved_path.is_file():
            return PythonAnalysis(
                path=resolved_path,
                issues=[
                    ParseIssue(
                        category="read_error",
                        message="Python source path is not a file.",
                    )
                ],
            )

        try:
            encoding = self._detect_encoding(resolved_path)
            source = resolved_path.read_text(
                encoding=encoding,
                errors="strict",
            )
        except (OSError, UnicodeError, SyntaxError) as error:
            return PythonAnalysis(
                path=resolved_path,
                issues=[
                    ParseIssue(
                        category="read_error",
                        message=str(error),
                    )
                ],
            )

        return self.parse_source(
            source,
            path=resolved_path,
            encoding=encoding,
        )

    def parse_source(
        self,
        source: str,
        *,
        path: Path | None = None,
        encoding: str = "utf-8",
    ) -> PythonAnalysis:
        source_path = (
            path.resolve()
            if path is not None
            else Path("<memory>")
        )

        analysis = PythonAnalysis(
            path=source_path,
            encoding=encoding,
            source_size=len(source.encode(encoding, errors="replace")),
            line_count=self._count_lines(source),
        )

        try:
            tree = ast.parse(
                source,
                filename=str(source_path),
                type_comments=True,
            )
        except SyntaxError as error:
            analysis.issues.append(
                ParseIssue(
                    category="syntax_error",
                    message=error.msg,
                    line_number=error.lineno,
                    column_offset=error.offset,
                )
            )
            return analysis

        analysis.module_docstring = ast.get_docstring(
            tree,
            clean=True,
        )
        analysis.imports = self._extract_imports(tree)
        analysis.functions = self._extract_module_functions(tree)
        analysis.classes = self._extract_module_classes(tree)
        analysis.module_attributes = self._extract_module_attributes(
            tree
        )
        analysis.exported_names = self._extract_exports(tree)

        return analysis

    def _extract_imports(
        self,
        tree: ast.Module,
    ) -> list[ImportReference]:
        imports: list[ImportReference] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                aliases = tuple(
                    (alias.name, alias.asname)
                    for alias in node.names
                )

                imports.append(
                    ImportReference(
                        module="",
                        names=tuple(
                            alias.name
                            for alias in node.names
                        ),
                        aliases=aliases,
                        level=0,
                        line_number=node.lineno,
                    )
                )

            elif isinstance(node, ast.ImportFrom):
                aliases = tuple(
                    (alias.name, alias.asname)
                    for alias in node.names
                )

                imports.append(
                    ImportReference(
                        module=node.module or "",
                        names=tuple(
                            alias.name
                            for alias in node.names
                        ),
                        aliases=aliases,
                        level=node.level,
                        line_number=node.lineno,
                    )
                )

        return sorted(
            imports,
            key=lambda item: (
                item.line_number,
                item.dotted_module,
                item.names,
            ),
        )

    def _extract_module_functions(
        self,
        tree: ast.Module,
    ) -> list[FunctionReference]:
        functions: list[FunctionReference] = []

        for node in tree.body:
            if isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            ):
                functions.append(
                    self._build_function_reference(
                        node,
                        parent_name=None,
                    )
                )

        return functions

    def _extract_module_classes(
        self,
        tree: ast.Module,
    ) -> list[ClassReference]:
        classes: list[ClassReference] = []

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                classes.append(
                    self._build_class_reference(
                        node,
                        parent_name=None,
                    )
                )

        return classes

    def _build_class_reference(
        self,
        node: ast.ClassDef,
        *,
        parent_name: str | None,
    ) -> ClassReference:
        qualified_name = (
            f"{parent_name}.{node.name}"
            if parent_name
            else node.name
        )

        decorators = tuple(
            self._build_decorator_reference(decorator)
            for decorator in node.decorator_list
        )

        bases = tuple(
            self._safe_unparse(base)
            for base in node.bases
        )

        methods: list[FunctionReference] = []
        nested_classes: list[ClassReference] = []

        for child in node.body:
            if isinstance(
                child,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            ):
                methods.append(
                    self._build_function_reference(
                        child,
                        parent_name=qualified_name,
                    )
                )
            elif isinstance(child, ast.ClassDef):
                nested_classes.append(
                    self._build_class_reference(
                        child,
                        parent_name=qualified_name,
                    )
                )

        base_names = {
            self._terminal_name(base)
            for base in bases
        }
        decorator_names = {
            decorator.name
            for decorator in decorators
        }

        is_dataclass = bool(
            decorator_names
            & {
                "dataclass",
                "dataclasses.dataclass",
                "pydantic.dataclasses.dataclass",
            }
        )

        is_enum = bool(
            base_names
            & {
                "Enum",
                "IntEnum",
                "StrEnum",
                "Flag",
                "IntFlag",
            }
        )

        is_protocol = "Protocol" in base_names

        is_abstract = bool(
            base_names
            & {
                "ABC",
                "ABCMeta",
            }
        ) or any(
            decorator.name in {
                "abstractmethod",
                "abc.abstractmethod",
            }
            for method in methods
            for decorator in method.decorators
        )

        return ClassReference(
            name=node.name,
            qualified_name=qualified_name,
            line_number=node.lineno,
            end_line_number=getattr(
                node,
                "end_lineno",
                None,
            ),
            visibility=self._visibility(node.name),
            bases=bases,
            decorators=decorators,
            docstring=ast.get_docstring(
                node,
                clean=True,
            ),
            methods=tuple(methods),
            nested_classes=tuple(nested_classes),
            class_attributes=tuple(
                self._extract_class_attributes(node)
            ),
            is_dataclass=is_dataclass,
            is_enum=is_enum,
            is_protocol=is_protocol,
            is_abstract=is_abstract,
        )

    def _build_function_reference(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        *,
        parent_name: str | None,
    ) -> FunctionReference:
        qualified_name = (
            f"{parent_name}.{node.name}"
            if parent_name
            else node.name
        )

        decorators = tuple(
            self._build_decorator_reference(decorator)
            for decorator in node.decorator_list
        )

        decorator_names = {
            decorator.name
            for decorator in decorators
        }

        return FunctionReference(
            name=node.name,
            qualified_name=qualified_name,
            line_number=node.lineno,
            end_line_number=getattr(
                node,
                "end_lineno",
                None,
            ),
            is_async=isinstance(
                node,
                ast.AsyncFunctionDef,
            ),
            is_method=parent_name is not None,
            is_property=bool(
                decorator_names
                & {
                    "property",
                    "cached_property",
                    "functools.cached_property",
                }
            ),
            visibility=self._visibility(node.name),
            arguments=tuple(
                self._extract_arguments(node.args)
            ),
            returns=(
                self._safe_unparse(node.returns)
                if node.returns is not None
                else None
            ),
            decorators=decorators,
            docstring=ast.get_docstring(
                node,
                clean=True,
            ),
            raises=tuple(
                self._extract_raised_exceptions(node)
            ),
            calls=tuple(
                self._extract_calls(node)
            ),
        )

    def _extract_arguments(
        self,
        arguments: ast.arguments,
    ) -> list[ArgumentInfo]:
        output: list[ArgumentInfo] = []

        positional = [
            *arguments.posonlyargs,
            *arguments.args,
        ]
        positional_defaults = [
            None
        ] * (
            len(positional) - len(arguments.defaults)
        ) + list(arguments.defaults)

        positional_only_count = len(
            arguments.posonlyargs
        )

        for index, (argument, default) in enumerate(
            zip(
                positional,
                positional_defaults,
                strict=True,
            )
        ):
            kind = (
                "positional_only"
                if index < positional_only_count
                else "positional_or_keyword"
            )

            output.append(
                ArgumentInfo(
                    name=argument.arg,
                    kind=kind,
                    annotation=self._annotation(argument),
                    default=(
                        self._safe_unparse(default)
                        if default is not None
                        else None
                    ),
                )
            )

        if arguments.vararg is not None:
            output.append(
                ArgumentInfo(
                    name=arguments.vararg.arg,
                    kind="var_positional",
                    annotation=self._annotation(
                        arguments.vararg
                    ),
                )
            )

        for argument, default in zip(
            arguments.kwonlyargs,
            arguments.kw_defaults,
            strict=True,
        ):
            output.append(
                ArgumentInfo(
                    name=argument.arg,
                    kind="keyword_only",
                    annotation=self._annotation(argument),
                    default=(
                        self._safe_unparse(default)
                        if default is not None
                        else None
                    ),
                )
            )

        if arguments.kwarg is not None:
            output.append(
                ArgumentInfo(
                    name=arguments.kwarg.arg,
                    kind="var_keyword",
                    annotation=self._annotation(
                        arguments.kwarg
                    ),
                )
            )

        return output

    def _extract_raised_exceptions(
        self,
        function_node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> list[str]:
        raised: set[str] = set()

        for node in self._walk_without_nested_definitions(
            function_node
        ):
            if not isinstance(node, ast.Raise):
                continue

            if node.exc is None:
                raised.add("<reraised>")
                continue

            expression = node.exc

            if isinstance(expression, ast.Call):
                expression = expression.func

            exception_name = self._safe_unparse(
                expression
            )

            if exception_name:
                raised.add(exception_name)

        return sorted(raised)

    def _extract_calls(
        self,
        function_node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> list[str]:
        calls: set[str] = set()

        for node in self._walk_without_nested_definitions(
            function_node
        ):
            if not isinstance(node, ast.Call):
                continue

            call_name = self._safe_unparse(node.func)

            if call_name:
                calls.add(call_name)

        return sorted(calls)

    def _extract_module_attributes(
        self,
        tree: ast.Module,
    ) -> list[str]:
        names: set[str] = set()

        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    names.update(
                        self._extract_assignment_names(
                            target
                        )
                    )

            elif isinstance(node, ast.AnnAssign):
                names.update(
                    self._extract_assignment_names(
                        node.target
                    )
                )

        return sorted(names)

    def _extract_class_attributes(
        self,
        node: ast.ClassDef,
    ) -> list[str]:
        names: set[str] = set()

        for child in node.body:
            if isinstance(child, ast.Assign):
                for target in child.targets:
                    names.update(
                        self._extract_assignment_names(
                            target
                        )
                    )

            elif isinstance(child, ast.AnnAssign):
                names.update(
                    self._extract_assignment_names(
                        child.target
                    )
                )

        return sorted(names)

    def _extract_exports(
        self,
        tree: ast.Module,
    ) -> list[str]:
        for node in tree.body:
            value: ast.expr | None = None

            if isinstance(node, ast.Assign):
                if any(
                    isinstance(target, ast.Name)
                    and target.id == "__all__"
                    for target in node.targets
                ):
                    value = node.value

            elif (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id == "__all__"
            ):
                value = node.value

            if value is None:
                continue

            exports = self._literal_string_sequence(
                value
            )

            if exports is not None:
                return sorted(set(exports))

        return []

    def _build_decorator_reference(
        self,
        node: ast.expr,
    ) -> DecoratorReference:
        expression = self._safe_unparse(node)
        name = self._decorator_name(node)

        return DecoratorReference(
            name=name,
            expression=expression,
            line_number=getattr(
                node,
                "lineno",
                0,
            ),
        )

    @staticmethod
    def _decorator_name(
        node: ast.expr,
    ) -> str:
        target = node.func if isinstance(
            node,
            ast.Call,
        ) else node

        try:
            return ast.unparse(target)
        except (AttributeError, ValueError):
            return target.__class__.__name__

    @staticmethod
    def _annotation(
        argument: ast.arg,
    ) -> str | None:
        if argument.annotation is None:
            return None

        return PythonSourceParser._safe_unparse(
            argument.annotation
        )

    @staticmethod
    def _extract_assignment_names(
        node: ast.expr,
    ) -> set[str]:
        names: set[str] = set()

        if isinstance(node, ast.Name):
            names.add(node.id)

        elif isinstance(
            node,
            (ast.Tuple, ast.List),
        ):
            for element in node.elts:
                names.update(
                    PythonSourceParser
                    ._extract_assignment_names(element)
                )

        return names

    @staticmethod
    def _literal_string_sequence(
        node: ast.expr,
    ) -> list[str] | None:
        if not isinstance(
            node,
            (ast.List, ast.Tuple, ast.Set),
        ):
            return None

        values: list[str] = []

        for element in node.elts:
            if not (
                isinstance(element, ast.Constant)
                and isinstance(element.value, str)
            ):
                return None

            values.append(element.value)

        return values

    @staticmethod
    def _walk_without_nested_definitions(
        root: ast.AST,
    ) -> Iterator[ast.AST]:
        """
        Walk one function while excluding nested function and class bodies.

        Calls and raises inside nested definitions belong to those definitions,
        not to the containing function.
        """

        stack: list[ast.AST] = []

        for child in reversed(
            list(ast.iter_child_nodes(root))
        ):
            stack.append(child)

        while stack:
            node = stack.pop()
            yield node

            if isinstance(
                node,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                    ast.ClassDef,
                    ast.Lambda,
                ),
            ):
                continue

            children = list(
                ast.iter_child_nodes(node)
            )

            for child in reversed(children):
                stack.append(child)

    @staticmethod
    def _safe_unparse(
        node: ast.AST | None,
    ) -> str:
        if node is None:
            return ""

        try:
            return ast.unparse(node)
        except (
            AttributeError,
            ValueError,
            TypeError,
        ):
            return node.__class__.__name__

    @staticmethod
    def _terminal_name(
        expression: str,
    ) -> str:
        expression = expression.strip()

        if not expression:
            return ""

        return expression.rsplit(".", maxsplit=1)[-1]

    @staticmethod
    def _visibility(name: str) -> str:
        if name.startswith("__") and name.endswith("__"):
            return "dunder"

        if name.startswith("__"):
            return "private"

        if name.startswith("_"):
            return "protected"

        return "public"

    @staticmethod
    def _count_lines(source: str) -> int:
        if not source:
            return 0

        return source.count("\n") + (
            0 if source.endswith("\n") else 1
        )

    @staticmethod
    def _detect_encoding(path: Path) -> str:
        with path.open("rb") as source_file:
            encoding, _ = tokenize.detect_encoding(
                source_file.readline
            )

        return encoding


def parse_python_file(
    path: Path,
) -> PythonAnalysis:
    """
    Convenience function for parsing one Python file.
    """

    return PythonSourceParser().parse_file(path)


def parse_python_files(
    paths: Iterable[Path],
) -> list[PythonAnalysis]:
    """
    Parse multiple files deterministically.

    A failure in one file is represented in that file's PythonAnalysis and
    does not stop the remaining repository scan.
    """

    parser = PythonSourceParser()

    return [
        parser.parse_file(path)
        for path in sorted(
            paths,
            key=lambda item: item.as_posix(),
        )
    ]