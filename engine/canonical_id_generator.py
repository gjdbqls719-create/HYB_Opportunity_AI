from __future__ import annotations

import re
from abc import ABC, abstractmethod
from threading import Lock
from typing import Iterable


class CanonicalIdGenerator(ABC):
    """
    Canonical Product의 표시용 ID를 생성하는 인터페이스.

    Catalog Manager는 구체적인 저장 방식이나 번호 관리 방식에
    직접 의존하지 않고 이 인터페이스만 사용한다.
    """

    @abstractmethod
    def generate(self) -> str:
        """
        새로운 Canonical Product 표시용 ID를 생성한다.
        """
        raise NotImplementedError


class InMemoryCanonicalIdGenerator(
    CanonicalIdGenerator
):
    """
    메모리에서 증가 번호를 관리하는 Canonical ID 생성기.

    기본 생성 형식:

        CP-000001
        CP-000002
        CP-000003

    현재 개발 및 테스트 단계에서 사용한다.

    이 구현체는 프로세스가 종료되면 현재 번호를 잃기 때문에,
    실제 운영 환경에서는 데이터베이스 기반 생성기로 교체해야 한다.
    """

    def __init__(
        self,
        *,
        prefix: str = "CP",
        start: int = 1,
        width: int = 6,
    ) -> None:
        self._prefix = self._validate_prefix(
            prefix
        )
        self._width = self._validate_positive_integer(
            width,
            field_name="width",
        )
        self._next_sequence = (
            self._validate_positive_integer(
                start,
                field_name="start",
            )
        )
        self._lock = Lock()

        self._display_id_pattern = re.compile(
            rf"^{re.escape(self._prefix)}-"
            rf"(\d{{{self._width},}})$"
        )

    @staticmethod
    def _validate_prefix(
        prefix: str,
    ) -> str:
        """
        ID 접두사를 검증한다.

        접두사는 대문자 영문자와 숫자만 허용한다.
        """
        if not isinstance(prefix, str):
            raise TypeError(
                "prefix는 문자열이어야 합니다."
            )

        normalized = prefix.strip()

        if not normalized:
            raise ValueError(
                "prefix는 비어 있을 수 없습니다."
            )

        if not re.fullmatch(
            r"[A-Z][A-Z0-9]*",
            normalized,
        ):
            raise ValueError(
                "prefix는 대문자 영문자로 시작하고 "
                "대문자 영문자와 숫자만 포함해야 합니다."
            )

        return normalized

    @staticmethod
    def _validate_positive_integer(
        value: int,
        *,
        field_name: str,
    ) -> int:
        """
        bool을 제외한 양의 정수인지 검증한다.
        """
        if isinstance(value, bool) or not isinstance(
            value,
            int,
        ):
            raise TypeError(
                f"{field_name}는 정수여야 합니다."
            )

        if value < 1:
            raise ValueError(
                f"{field_name}는 1 이상이어야 합니다."
            )

        return value

    @property
    def prefix(self) -> str:
        """
        ID 접두사를 반환한다.
        """
        return self._prefix

    @property
    def width(self) -> int:
        """
        번호 부분의 최소 자릿수를 반환한다.
        """
        return self._width

    @property
    def next_sequence(self) -> int:
        """
        다음에 발급될 번호를 반환한다.

        확인용 속성이며 번호를 소비하지 않는다.
        """
        with self._lock:
            return self._next_sequence

    def _format_display_id(
        self,
        sequence: int,
    ) -> str:
        """
        정수 번호를 표시용 ID로 변환한다.
        """
        return (
            f"{self._prefix}-"
            f"{sequence:0{self._width}d}"
        )

    def generate(self) -> str:
        """
        새로운 표시용 ID를 발급한다.

        Lock을 사용하므로 하나의 프로세스 안에서 여러 스레드가
        동시에 호출해도 중복 ID가 발급되지 않는다.
        """
        with self._lock:
            sequence = self._next_sequence
            self._next_sequence += 1

        return self._format_display_id(
            sequence
        )

    def synchronize(
        self,
        existing_display_ids: Iterable[str],
    ) -> None:
        """
        기존 Canonical Product ID를 확인해 다음 번호를 조정한다.

        예:
            기존 ID:
                CP-000001
                CP-000005
                CP-000012

            동기화 이후 다음 ID:
                CP-000013

        다른 접두사를 사용하거나 형식이 맞지 않는 ID는 무시한다.
        현재 번호보다 낮은 ID도 영향을 주지 않는다.
        """
        if isinstance(
            existing_display_ids,
            (str, bytes),
        ):
            raise TypeError(
                "existing_display_ids는 문자열 컬렉션이어야 합니다."
            )

        try:
            iterator = iter(
                existing_display_ids
            )
        except TypeError as error:
            raise TypeError(
                "existing_display_ids는 반복 가능한 객체여야 합니다."
            ) from error

        highest_sequence: int | None = None

        for display_id in iterator:
            if not isinstance(display_id, str):
                raise TypeError(
                    "기존 display_id는 문자열이어야 합니다."
                )

            match = self._display_id_pattern.fullmatch(
                display_id.strip()
            )

            if match is None:
                continue

            sequence = int(
                match.group(1)
            )

            if (
                highest_sequence is None
                or sequence > highest_sequence
            ):
                highest_sequence = sequence

        if highest_sequence is None:
            return

        with self._lock:
            required_next_sequence = (
                highest_sequence + 1
            )

            if (
                required_next_sequence
                > self._next_sequence
            ):
                self._next_sequence = (
                    required_next_sequence
                )