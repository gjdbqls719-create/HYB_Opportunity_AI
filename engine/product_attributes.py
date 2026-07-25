from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _normalize_optional_text(
    value: Any,
) -> str | None:
    """
    선택적 문자열을 비교하기 쉬운 형태로 정리한다.
    """
    if value is None:
        return None

    normalized = str(value).strip().lower()

    if not normalized:
        return None

    return normalized


def _normalize_tokens(
    values: Any,
) -> tuple[str, ...]:
    """
    토큰 목록을 소문자, 중복 제거, 정렬된 tuple로 변환한다.
    """
    if values is None:
        return ()

    normalized_tokens = {
        str(value).strip().lower()
        for value in values
        if str(value).strip()
    }

    return tuple(sorted(normalized_tokens))


@dataclass(frozen=True, slots=True)
class ProductAttributes:
    """
    상품 제목과 Product 데이터에서 추출한 공통 속성.

    특정 상품군에 종속되지 않도록 범용 필드를 사용한다.
    추출할 수 없는 값은 None으로 유지한다.
    """

    normalized_title: str

    brand: str | None = None
    model_number: str | None = None
    category: str | None = None

    capacity: str | None = None
    color: str | None = None
    size: str | None = None
    edition: str | None = None
    condition: str | None = None

    quantity: int | None = None
    is_bundle: bool = False
    is_accessory: bool = False

    tokens: tuple[str, ...] = field(
        default_factory=tuple
    )

    def __post_init__(self) -> None:
        normalized_title = str(
            self.normalized_title
        ).strip().lower()

        if not normalized_title:
            raise ValueError(
                "정규화된 상품명은 비어 있을 수 없습니다."
            )

        brand = _normalize_optional_text(
            self.brand
        )
        model_number = _normalize_optional_text(
            self.model_number
        )
        category = _normalize_optional_text(
            self.category
        )
        capacity = _normalize_optional_text(
            self.capacity
        )
        color = _normalize_optional_text(
            self.color
        )
        size = _normalize_optional_text(
            self.size
        )
        edition = _normalize_optional_text(
            self.edition
        )
        condition = _normalize_optional_text(
            self.condition
        )

        quantity = self.quantity

        if quantity is not None:
            try:
                quantity = int(quantity)
            except Exception as error:
                raise ValueError(
                    "상품 수량은 정수여야 합니다."
                ) from error

            if quantity <= 0:
                raise ValueError(
                    "상품 수량은 1 이상이어야 합니다."
                )

        tokens = _normalize_tokens(
            self.tokens
        )

        object.__setattr__(
            self,
            "normalized_title",
            normalized_title,
        )
        object.__setattr__(
            self,
            "brand",
            brand,
        )
        object.__setattr__(
            self,
            "model_number",
            model_number,
        )
        object.__setattr__(
            self,
            "category",
            category,
        )
        object.__setattr__(
            self,
            "capacity",
            capacity,
        )
        object.__setattr__(
            self,
            "color",
            color,
        )
        object.__setattr__(
            self,
            "size",
            size,
        )
        object.__setattr__(
            self,
            "edition",
            edition,
        )
        object.__setattr__(
            self,
            "condition",
            condition,
        )
        object.__setattr__(
            self,
            "quantity",
            quantity,
        )
        object.__setattr__(
            self,
            "is_bundle",
            bool(self.is_bundle),
        )
        object.__setattr__(
            self,
            "is_accessory",
            bool(self.is_accessory),
        )
        object.__setattr__(
            self,
            "tokens",
            tokens,
        )

    def to_dict(self) -> dict[str, Any]:
        """
        저장, 화면 표시, API 응답에 사용할 수 있는 dict로 변환한다.
        """
        return {
            "normalized_title": self.normalized_title,
            "brand": self.brand,
            "model_number": self.model_number,
            "category": self.category,
            "capacity": self.capacity,
            "color": self.color,
            "size": self.size,
            "edition": self.edition,
            "condition": self.condition,
            "quantity": self.quantity,
            "is_bundle": self.is_bundle,
            "is_accessory": self.is_accessory,
            "tokens": list(self.tokens),
        }


@dataclass(frozen=True, slots=True)
class AttributeConflict:
    """
    두 상품의 중요 속성이 서로 다른 경우를 나타낸다.

    예:
        capacity: 128gb ↔ 256gb
        size: us 9 ↔ us 10
    """

    field_name: str
    left_value: str
    right_value: str
    severity: str = "high"

    def __post_init__(self) -> None:
        field_name = str(
            self.field_name
        ).strip().lower()
        left_value = str(
            self.left_value
        ).strip().lower()
        right_value = str(
            self.right_value
        ).strip().lower()
        severity = str(
            self.severity
        ).strip().lower()

        if not field_name:
            raise ValueError(
                "충돌 필드 이름은 비어 있을 수 없습니다."
            )

        if not left_value or not right_value:
            raise ValueError(
                "충돌 값은 비어 있을 수 없습니다."
            )

        if severity not in {
            "low",
            "medium",
            "high",
        }:
            raise ValueError(
                "충돌 심각도는 low, medium, high 중 "
                "하나여야 합니다."
            )

        object.__setattr__(
            self,
            "field_name",
            field_name,
        )
        object.__setattr__(
            self,
            "left_value",
            left_value,
        )
        object.__setattr__(
            self,
            "right_value",
            right_value,
        )
        object.__setattr__(
            self,
            "severity",
            severity,
        )


@dataclass(frozen=True, slots=True)
class AttributeComparison:
    """
    두 상품 속성의 일치 및 충돌 결과.
    """

    matched_fields: tuple[str, ...] = field(
        default_factory=tuple
    )
    conflicts: tuple[AttributeConflict, ...] = field(
        default_factory=tuple
    )

    def __post_init__(self) -> None:
        matched_fields = tuple(
            sorted(
                {
                    str(field_name).strip().lower()
                    for field_name in self.matched_fields
                    if str(field_name).strip()
                }
            )
        )

        conflicts = tuple(
            self.conflicts
        )

        for conflict in conflicts:
            if not isinstance(
                conflict,
                AttributeConflict,
            ):
                raise TypeError(
                    "모든 충돌 정보는 "
                    "AttributeConflict여야 합니다."
                )

        object.__setattr__(
            self,
            "matched_fields",
            matched_fields,
        )
        object.__setattr__(
            self,
            "conflicts",
            conflicts,
        )

    @property
    def has_conflict(self) -> bool:
        return bool(self.conflicts)

    @property
    def has_high_conflict(self) -> bool:
        return any(
            conflict.severity == "high"
            for conflict in self.conflicts
        )