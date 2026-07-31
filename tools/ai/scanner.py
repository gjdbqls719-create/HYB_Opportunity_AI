from __future__ import annotations

from pathlib import Path

from .config import (
    CODE_EXTENSIONS,
    CONFIG_EXTENSIONS,
    DOCUMENT_EXTENSIONS,
    DOMAIN_KEYWORDS,
    ENTRY_POINT_FILES,
    ENTRY_POINT_SUFFIXES,
    IGNORE_DIRS,
    IGNORE_FILES,
)
from .models import (
    ConfigFile,
    DirectoryNode,
    Domain,
    EntryPoint,
    MarkdownFile,
    ProjectModel,
    PythonFile,
)
from .parser import PythonSourceParser


class ProjectScanner:
    """
    HYB 저장소를 스캔하여 ProjectModel을 생성한다.

    Python 파일 분석은 PythonSourceParser에 위임한다.
    Scanner는 다음 책임만 가진다.

    - 저장소 디렉터리 탐색
    - 파일 유형 분류
    - PythonAnalysis 연결
    - Markdown 메타데이터 추출
    - 진입점 탐지
    - 논리 도메인 구성

    Python AST 분석 결과의 단일 진실 공급원은
    PythonFile.analysis에 저장된 PythonAnalysis다.
    """

    def __init__(
        self,
        root: Path,
        *,
        python_parser: PythonSourceParser | None = None,
    ) -> None:
        self.root = root.resolve()
        self.python_parser = python_parser or PythonSourceParser()

    def scan(self) -> ProjectModel:
        """
        저장소 전체를 스캔한다.

        Returns
        -------
        ProjectModel
            디렉터리, 파일, 진입점, 도메인 및 Python 분석 결과를
            포함하는 프로젝트 모델.

        Raises
        ------
        FileNotFoundError
            저장소 루트가 존재하지 않을 때.
        NotADirectoryError
            저장소 루트가 디렉터리가 아닐 때.
        """
        self._validate_root()

        model = ProjectModel(root=self.root)

        self._scan_directories(model)
        self._scan_files(model)
        self._build_domains(model)

        return model

    # ---------------------------------------------------------
    # Root Validation
    # ---------------------------------------------------------

    def _validate_root(self) -> None:
        if not self.root.exists():
            raise FileNotFoundError(
                f"Project root does not exist: {self.root}"
            )

        if not self.root.is_dir():
            raise NotADirectoryError(
                f"Project root is not a directory: {self.root}"
            )

    # ---------------------------------------------------------
    # Directory Scan
    # ---------------------------------------------------------

    def _scan_directories(
        self,
        model: ProjectModel,
    ) -> None:
        """
        무시 대상이 아닌 모든 디렉터리를 수집한다.

        각 DirectoryNode에는 다음 정보가 포함된다.

        - 디렉터리 바로 아래의 파일
        - 디렉터리 바로 아래의 하위 디렉터리
        """
        directory_nodes: dict[Path, DirectoryNode] = {}

        for directory in self._iter_directories():
            directory_nodes[directory] = DirectoryNode(
                path=directory,
            )

        for directory, node in directory_nodes.items():
            try:
                children = sorted(
                    directory.iterdir(),
                    key=lambda item: item.as_posix(),
                )
            except OSError:
                continue

            for child in children:
                if self._ignore(child):
                    continue

                if child.is_file():
                    node.add_file(child)

                elif child.is_dir():
                    child_node = directory_nodes.get(
                        child.resolve()
                    )

                    if child_node is not None:
                        node.add_child(child_node)

        for node in sorted(
            directory_nodes.values(),
            key=lambda item: item.path.as_posix(),
        ):
            model.add_directory(node)

    def _iter_directories(self):
        """
        프로젝트 루트와 모든 유효한 하위 디렉터리를 반환한다.
        """
        if not self._ignore(self.root):
            yield self.root

        for directory in sorted(
            self.root.rglob("*"),
            key=lambda item: item.as_posix(),
        ):
            if not directory.is_dir():
                continue

            if self._ignore(directory):
                continue

            yield directory.resolve()

    # ---------------------------------------------------------
    # File Scan
    # ---------------------------------------------------------

    def _scan_files(
        self,
        model: ProjectModel,
    ) -> None:
        for file in self._iter_files():
            suffix = file.suffix.lower()

            if suffix in CODE_EXTENSIONS:
                model.add_python(
                    self._scan_python(file)
                )

            elif suffix in DOCUMENT_EXTENSIONS:
                model.add_markdown(
                    self._scan_markdown(file)
                )

            elif suffix in CONFIG_EXTENSIONS:
                model.add_config(
                    self._scan_config(file)
                )

            self._detect_entry_point(
                file,
                model,
            )

    def _iter_files(self):
        """
        무시 대상이 아닌 모든 파일을 결정적 순서로 반환한다.
        """
        for file in sorted(
            self.root.rglob("*"),
            key=lambda item: item.as_posix(),
        ):
            if not file.is_file():
                continue

            if self._ignore(file):
                continue

            yield file.resolve()

    # ---------------------------------------------------------
    # Python Parser
    # ---------------------------------------------------------

    def _scan_python(
        self,
        path: Path,
    ) -> PythonFile:
        """
        PythonSourceParser를 이용해 Python 파일을 분석한다.

        읽기 또는 문법 오류는 PythonAnalysis.issues에 기록되며
        저장소 전체 스캔은 계속 진행된다.
        """
        analysis = self.python_parser.parse_file(path)

        return PythonFile(
            path=path,
            extension=path.suffix.lower(),
            size=self._safe_file_size(path),
            analysis=analysis,
        )

    # ---------------------------------------------------------
    # Markdown Parser
    # ---------------------------------------------------------

    def _scan_markdown(
        self,
        path: Path,
    ) -> MarkdownFile:
        title = ""
        headings: list[str] = []

        try:
            lines = path.read_text(
                encoding="utf-8",
                errors="replace",
            ).splitlines()
        except OSError:
            lines = []

        for line in lines:
            stripped = line.lstrip()

            if not stripped.startswith("#"):
                continue

            heading = stripped.lstrip("#").strip()

            if not heading:
                continue

            headings.append(heading)

            if not title:
                title = heading

        return MarkdownFile(
            path=path,
            extension=path.suffix.lower(),
            size=self._safe_file_size(path),
            title=title,
            headings=headings,
        )

    # ---------------------------------------------------------
    # Config Scanner
    # ---------------------------------------------------------

    def _scan_config(
        self,
        path: Path,
    ) -> ConfigFile:
        return ConfigFile(
            path=path,
            extension=path.suffix.lower(),
            size=self._safe_file_size(path),
        )

    # ---------------------------------------------------------
    # Entry Point Detection
    # ---------------------------------------------------------

    def _detect_entry_point(
        self,
        file: Path,
        model: ProjectModel,
    ) -> None:
        reason = self._entry_point_reason(file)

        if reason is None:
            return

        if any(
            entry.path == file
            for entry in model.entry_points
        ):
            return

        model.add_entry_point(
            EntryPoint(
                path=file,
                reason=reason,
            )
        )

    def _entry_point_reason(
        self,
        file: Path,
    ) -> str | None:
        file_name = file.name
        lower_name = file_name.lower()
        lower_stem = file.stem.lower()

        if file_name in ENTRY_POINT_FILES:
            return "well-known entry point"

        for suffix in ENTRY_POINT_SUFFIXES:
            if file_name.endswith(suffix):
                return "entry suffix"

        if "cli" in lower_stem:
            return "cli module"

        if lower_name == "__main__.py":
            return "python module entry point"

        return None

    # ---------------------------------------------------------
    # Domain Builder
    # ---------------------------------------------------------

    def _build_domains(
        self,
        model: ProjectModel,
    ) -> None:
        domain_map: dict[str, Domain] = {}

        for python_file in model.python_files:
            searchable_path = self._relative_path(
                python_file.path
            ).as_posix().lower()

            for domain_name, keywords in DOMAIN_KEYWORDS.items():
                normalized_keywords = (
                    keyword.lower()
                    for keyword in keywords
                )

                if not any(
                    keyword in searchable_path
                    for keyword in normalized_keywords
                ):
                    continue

                domain = domain_map.setdefault(
                    domain_name,
                    Domain(name=domain_name),
                )
                domain.add_file(python_file.path)

        for domain in sorted(
            domain_map.values(),
            key=lambda item: item.name,
        ):
            domain.files.sort(
                key=lambda item: item.as_posix()
            )
            model.add_domain(domain)

    # ---------------------------------------------------------
    # Ignore Rules
    # ---------------------------------------------------------

    def _ignore(
        self,
        path: Path,
    ) -> bool:
        """
        IGNORE_DIRS와 IGNORE_FILES 규칙을 적용한다.

        절대 경로의 상위 시스템 경로가 아니라 프로젝트 루트 기준
        상대 경로 부분만 검사하여 우연한 이름 충돌을 방지한다.
        """
        relative_path = self._relative_path(path)

        if any(
            part in IGNORE_DIRS
            for part in relative_path.parts
        ):
            return True

        if path.name in IGNORE_FILES:
            return True

        return False

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------

    def _relative_path(
        self,
        path: Path,
    ) -> Path:
        try:
            return path.resolve().relative_to(
                self.root
            )
        except ValueError:
            return path

    @staticmethod
    def _safe_file_size(
        path: Path,
    ) -> int:
        try:
            return path.stat().st_size
        except OSError:
            return 0


def scan_project(
    root: Path,
) -> ProjectModel:
    """
    프로젝트 스캔 편의 함수.
    """
    return ProjectScanner(root).scan()