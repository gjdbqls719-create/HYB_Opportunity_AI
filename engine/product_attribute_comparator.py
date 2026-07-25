from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from engine.product_attributes import (
    AttributeComparison,
    AttributeConflict,
    ProductAttributes,
)


HIGH_CONFLICT_FIELDS: frozenset[str] = frozenset(
    {
        "brand",
        "model_number",
        "capacity",
        "size",
        "quantity",
        "is_accessory",
    }
)

MEDIUM_CONFLICT_FIELDS: frozenset[str] = frozenset(
    {
        "category",
        "edition",
        "is_bundle",
    }
)

LOW_CONFLICT_FIELDS: frozenset[str] = frozenset(
    {
        "color",
        "condition",
    }
)


@dataclass(frozen=True, slots=True)
class AttributeFieldRule:
    """
    상품 속성 하나를 비교하기 위한 규칙.

    field_name:
        ProductAttributes의 필드 이름.

    severity:
        값이 다를 때 기록할 충돌 심각도.

    ignore_when_missing:
        한쪽 또는 양쪽 값이 없을 때 비교를 생략할지 여부.
    """

    field_name: str
    severity: str
    ignore_when_missing: bool = True

    def __post_init__(self) -> None:
        field_name = str(
            self.field_name
        ).strip()

        severity = str(
            self.severity
        ).strip().lower()

        if not field_name:
            raise ValueError(
                "비교 필드 이름은 비어 있을 수 없습니다."
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
            "severity",
            severity,
        )
        object.__setattr__(
            self,
            "ignore_when_missing",
            bool(self.ignore_when_missing),
        )


DEFAULT_ATTRIBUTE_RULES: tuple[
    AttributeFieldRule,
    ...,
] = (
    AttributeFieldRule(
        field_name="brand",
        severity="high",
    ),
    AttributeFieldRule(
        field_name="model_number",
        severity="high",
    ),
    AttributeFieldRule(
        field_name="category",
        severity="medium",
    ),
    AttributeFieldRule(
        field_name="capacity",
        severity="high",
    ),
    AttributeFieldRule(
        field_name="color",
        severity="low",
    ),
    AttributeFieldRule(
        field_name="size",
        severity="high",
    ),
    AttributeFieldRule(
        field_name="edition",
        severity="medium",
    ),
    AttributeFieldRule(
        field_name="condition",
        severity="low",
    ),
    AttributeFieldRule(
        field_name="quantity",
        severity="high",
    ),
    AttributeFieldRule(
        field_name="is_bundle",
        severity="medium",
        ignore_when_missing=False,
    ),
    AttributeFieldRule(
        field_name="is_accessory",
        severity="high",
        ignore_when_missing=False,
    ),
)


def _normalize_comparison_value(
    value: Any,
) -> str | None:
    """
    비교할 값을 일관된 문자열 형태로 변환한다.
    """
    if value is None:
        return None

    if isinstance(value, bool):
        return "true" if value else "false"

    if isinstance(value, str):
        normalized = " ".join(
            value.strip().lower().split()
        )

        return normalized or None

    normalized = str(value).strip().lower()

    return normalized or None


def _values_are_missing(
    left_value: str | None,
    right_value: str | None,
) -> bool:
    return (
        left_value is None
        or right_value is None
    )


def _compare_single_field(
    left: ProductAttributes,
    right: ProductAttributes,
    rule: AttributeFieldRule,
) -> tuple[
    str | None,
    AttributeConflict | None,
]:
    """
    속성 하나를 비교한다.

    반환값:
        일치한 필드명 또는 None
        충돌 정보 또는 None
    """
    if not hasattr(
        left,
        rule.field_name,
    ):
        raise AttributeError(
            f"ProductAttributes에 "
            f"'{rule.field_name}' 필드가 없습니다."
        )

    if not hasattr(
        right,
        rule.field_name,
    ):
        raise AttributeError(
            f"ProductAttributes에 "
            f"'{rule.field_name}' 필드가 없습니다."
        )

    left_value = _normalize_comparison_value(
        getattr(
            left,
            rule.field_name,
        )
    )
    right_value = _normalize_comparison_value(
        getattr(
            right,
            rule.field_name,
        )
    )

    if rule.ignore_when_missing and _values_are_missing(
        left_value,
        right_value,
    ):
        return None, None

    if (
        left_value is None
        and right_value is None
    ):
        return None, None

    if left_value == right_value:
        return rule.field_name, None

    return (
        None,
        AttributeConflict(
            field_name=rule.field_name,
            left_value=left_value or "unknown",
            right_value=right_value or "unknown",
            severity=rule.severity,
        ),
    )


def compare_product_attributes(
    left: ProductAttributes,
    right: ProductAttributes,
    *,
    rules: tuple[
        AttributeFieldRule,
        ...,
    ] = DEFAULT_ATTRIBUTE_RULES,
) -> AttributeComparison:
    """
    두 상품의 추출된 속성을 비교한다.

    속성이 둘 다 존재하면서 같은 경우:
        matched_fields에 추가한다.

    속성이 둘 다 존재하면서 다른 경우:
        conflicts에 추가한다.

    한쪽 속성이 없는 경우:
        기본적으로 판단을 보류하고 충돌로 기록하지 않는다.

    단, is_bundle과 is_accessory는 bool 값이므로
    False도 실제 정보로 간주하여 항상 비교한다.
    """
    if not isinstance(
        left,
        ProductAttributes,
    ):
        raise TypeError(
            "left는 ProductAttributes 객체여야 합니다."
        )

    if not isinstance(
        right,
        ProductAttributes,
    ):
        raise TypeError(
            "right는 ProductAttributes 객체여야 합니다."
        )

    matched_fields: list[str] = []
    conflicts: list[AttributeConflict] = []

    for rule in rules:
        if not isinstance(
            rule,
            AttributeFieldRule,
        ):
            raise TypeError(
                "모든 비교 규칙은 "
                "AttributeFieldRule 객체여야 합니다."
            )

        matched_field, conflict = (
            _compare_single_field(
                left,
                right,
                rule,
            )
        )

        if matched_field is not None:
            matched_fields.append(
                matched_field
            )

        if conflict is not None:
            conflicts.append(
                conflict
            )

    return AttributeComparison(
        matched_fields=tuple(
            matched_fields
        ),
        conflicts=tuple(
            conflicts
        ),
    )


def get_conflict_penalty(
    comparison: AttributeComparison,
) -> float:
    """
    속성 충돌을 상품 매칭 점수에서 차감하기 위한
    페널티 값으로 변환한다.

    현재 기준:
        high 충돌   = 35점
        medium 충돌 = 15점
        low 충돌    = 5점

    최종 연결 단계에서 0~100점 범위에 맞게 사용한다.
    """
    if not isinstance(
        comparison,
        AttributeComparison,
    ):
        raise TypeError(
            "comparison은 AttributeComparison "
            "객체여야 합니다."
        )

    penalty_by_severity: dict[str, float] = {
        "high": 35.0,
        "medium": 15.0,
        "low": 5.0,
    }

    penalty = sum(
        penalty_by_severity[
            conflict.severity
        ]
        for conflict in comparison.conflicts
    )

    return min(
        100.0,
        penalty,
    )


def has_identity_conflict(
    comparison: AttributeComparison,
) -> bool:
    """
    서로 다른 상품이라고 판단할 가능성이 매우 높은
    핵심 속성 충돌이 있는지 확인한다.

    색상이나 상태 차이는 핵심 상품 정체성 충돌로 보지 않는다.
    """
    if not isinstance(
        comparison,
        AttributeComparison,
    ):
        raise TypeError(
            "comparison은 AttributeComparison "
            "객체여야 합니다."
        )

    identity_fields = {
        "brand",
        "model_number",
        "capacity",
        "size",
        "quantity",
        "is_accessory",
    }

    return any(
        conflict.severity == "high"
        and conflict.field_name in identity_fields
        for conflict in comparison.conflicts
    )