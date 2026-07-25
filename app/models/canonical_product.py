from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Mapping
from uuid import UUID, uuid4


DISPLAY_ID_PATTERN = re.compile(
    r"^CP-\d{6,}$"
)


def _utc_now() -> datetime:
    """
    현재 UTC 시간을 timezone-aware datetime으로 반환한다.
    """
    return datetime.now(timezone.utc)


def _normalize_optional_text(
    value: str | None,
    *,
    field_name: str,
) -> str | None:
    """
    선택 문자열 필드를 정리한다.

    None은 그대로 유지하고, 문자열은 앞뒤 공백을 제거한다.
    공백만 존재하는 문자열은 None으로 변환한다.
    """
    if value is None:
        return None

    if not isinstance(value, str):
        raise TypeError(
            f"{field_name}은 문자열 또는 None이어야 합니다."
        )

    normalized = value.strip()

    if not normalized:
        return None

    return normalized


def _normalize_required_text(
    value: str,
    *,
    field_name: str,
) -> str:
    """
    필수 문자열 필드를 검증하고 앞뒤 공백을 제거한다.
    """
    if not isinstance(value, str):
        raise TypeError(
            f"{field_name}은 문자열이어야 합니다."
        )

    normalized = value.strip()

    if not normalized:
        raise ValueError(
            f"{field_name}은 비어 있을 수 없습니다."
        )

    return normalized


def _normalize_attributes(
    attributes: Mapping[str, str] | None,
) -> Mapping[str, str]:
    """
    확장 속성을 안전한 읽기 전용 매핑으로 변환한다.

    원본 딕셔너리를 복사하므로 모델 생성 이후 외부에서
    원본 딕셔너리를 변경해도 CanonicalProduct에는 영향을 주지 않는다.
    """
    if attributes is None:
        return MappingProxyType({})

    if not isinstance(attributes, Mapping):
        raise TypeError(
            "attributes는 Mapping 객체여야 합니다."
        )

    normalized: dict[str, str] = {}

    for key, value in attributes.items():
        if not isinstance(key, str):
            raise TypeError(
                "attributes의 키는 문자열이어야 합니다."
            )

        if not isinstance(value, str):
            raise TypeError(
                "attributes의 값은 문자열이어야 합니다."
            )

        normalized_key = key.strip()
        normalized_value = value.strip()

        if not normalized_key:
            raise ValueError(
                "attributes의 키는 비어 있을 수 없습니다."
            )

        if not normalized_value:
            raise ValueError(
                "attributes의 값은 비어 있을 수 없습니다."
            )

        normalized[normalized_key] = normalized_value

    return MappingProxyType(normalized)


@dataclass(frozen=True, slots=True)
class CanonicalProduct:
    """
    HYB가 인식하는 하나의 실제 상품을 표현한다.

    Marketplace별 개별 상품 정보를 저장하는 Product와 달리,
    CanonicalProduct는 여러 Marketplace 상품이 공통으로 연결될
    수 있는 기준 상품이다.

    id:
        내부 데이터베이스 및 시스템 연결에 사용하는 UUID.

    display_id:
        사용자 화면, 로그 및 운영 문서에서 사용하는 식별자.
        예: CP-000001

    attributes:
        카테고리별 추가 사양을 저장하는 읽기 전용 확장 속성.
    """

    display_id: str

    brand: str | None = None
    model: str | None = None
    category: str | None = None

    capacity: str | None = None
    color: str | None = None
    size: str | None = None
    edition: str | None = None
    condition: str | None = None

    attributes: Mapping[str, str] = field(
        default_factory=dict
    )

    id: UUID = field(
        default_factory=uuid4
    )

    created_at: datetime = field(
        default_factory=_utc_now
    )
    updated_at: datetime = field(
        default_factory=_utc_now
    )

    def __post_init__(self) -> None:
        normalized_display_id = _normalize_required_text(
            self.display_id,
            field_name="display_id",
        )

        if not DISPLAY_ID_PATTERN.fullmatch(
            normalized_display_id
        ):
            raise ValueError(
                "display_id는 CP-000001 형식이어야 합니다."
            )

        if not isinstance(self.id, UUID):
            raise TypeError(
                "id는 UUID 객체여야 합니다."
            )

        if not isinstance(self.created_at, datetime):
            raise TypeError(
                "created_at은 datetime 객체여야 합니다."
            )

        if not isinstance(self.updated_at, datetime):
            raise TypeError(
                "updated_at은 datetime 객체여야 합니다."
            )

        if self.created_at.tzinfo is None:
            raise ValueError(
                "created_at은 timezone-aware datetime이어야 합니다."
            )

        if self.updated_at.tzinfo is None:
            raise ValueError(
                "updated_at은 timezone-aware datetime이어야 합니다."
            )

        if self.updated_at < self.created_at:
            raise ValueError(
                "updated_at은 created_at보다 빠를 수 없습니다."
            )

        object.__setattr__(
            self,
            "display_id",
            normalized_display_id,
        )

        text_fields = (
            "brand",
            "model",
            "category",
            "capacity",
            "color",
            "size",
            "edition",
            "condition",
        )

        for field_name in text_fields:
            normalized_value = _normalize_optional_text(
                getattr(self, field_name),
                field_name=field_name,
            )

            object.__setattr__(
                self,
                field_name,
                normalized_value,
            )

        object.__setattr__(
            self,
            "attributes",
            _normalize_attributes(
                self.attributes
            ),
        )

    @property
    def identity_summary(self) -> str:
        """
        상품의 주요 식별 정보를 사람이 읽기 쉬운 문자열로 반환한다.
        """
        parts = (
            self.brand,
            self.model,
            self.edition,
            self.capacity,
            self.color,
            self.size,
        )

        return " ".join(
            part
            for part in parts
            if part is not None
        )