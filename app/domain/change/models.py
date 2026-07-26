from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any


class ChangeDirection(str, Enum):
    """
    값의 변화 방향.

    숫자형 값은 증가 또는 감소로 표현하고,
    방향을 판단할 수 없는 문자열·식별자·상태 변경은
    CHANGED로 표현한다.
    """

    UNCHANGED = "unchanged"
    INCREASED = "increased"
    DECREASED = "decreased"
    CHANGED = "changed"


class ChangeType(str, Enum):
    """
    Change Domain에서 지원하는 변화 범주.
    """

    PRICE = "price"
    INVENTORY = "inventory"
    SELLER = "seller"


def _normalize_required_text(
    value: str,
    *,
    field_name: str,
) -> str:
    cleaned = value.strip()

    if not cleaned:
        raise ValueError(
            f"{field_name}은 비어 있을 수 없습니다."
        )

    return cleaned


def _normalize_optional_decimal(
    value: Decimal | int | float | str | None,
    *,
    field_name: str,
) -> Decimal | None:
    if value is None:
        return None

    try:
        normalized = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError(
            f"{field_name}은 유효한 숫자여야 합니다."
        ) from error

    if not normalized.is_finite():
        raise ValueError(
            f"{field_name}은 유한한 숫자여야 합니다."
        )

    return normalized


def _validate_aware_datetime(
    value: datetime,
    *,
    field_name: str,
) -> None:
    if value.tzinfo is None:
        raise ValueError(
            f"{field_name}은 timezone 정보가 필요합니다."
        )

    if value.utcoffset() is None:
        raise ValueError(
            f"{field_name}은 유효한 timezone 정보가 필요합니다."
        )


@dataclass(frozen=True, slots=True)
class DetectedChange:
    """
    단일 필드에서 발견된 변화.

    이전 값과 현재 값을 함께 보존하며,
    숫자형 변화의 경우 절대 변화량과 변화율을
    선택적으로 포함할 수 있다.
    """

    change_type: ChangeType
    field_name: str
    previous_value: Any
    current_value: Any
    direction: ChangeDirection
    absolute_change: Decimal | None = None
    percentage_change: Decimal | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.change_type, ChangeType):
            raise TypeError(
                "change_type은 ChangeType이어야 합니다."
            )

        if not isinstance(self.direction, ChangeDirection):
            raise TypeError(
                "direction은 ChangeDirection이어야 합니다."
            )

        normalized_field_name = _normalize_required_text(
            self.field_name,
            field_name="field_name",
        )

        normalized_absolute_change = (
            _normalize_optional_decimal(
                self.absolute_change,
                field_name="absolute_change",
            )
        )

        normalized_percentage_change = (
            _normalize_optional_decimal(
                self.percentage_change,
                field_name="percentage_change",
            )
        )

        values_are_equal = (
            self.previous_value == self.current_value
        )

        if (
            self.direction is ChangeDirection.UNCHANGED
            and not values_are_equal
        ):
            raise ValueError(
                "UNCHANGED 변화는 이전 값과 현재 값이 "
                "같아야 합니다."
            )

        if (
            self.direction is not ChangeDirection.UNCHANGED
            and values_are_equal
        ):
            raise ValueError(
                "변경된 방향을 사용하려면 이전 값과 "
                "현재 값이 달라야 합니다."
            )

        if (
            self.direction is ChangeDirection.INCREASED
            and normalized_absolute_change is not None
            and normalized_absolute_change < 0
        ):
            raise ValueError(
                "INCREASED의 absolute_change는 "
                "0보다 작을 수 없습니다."
            )

        if (
            self.direction is ChangeDirection.DECREASED
            and normalized_absolute_change is not None
            and normalized_absolute_change > 0
        ):
            raise ValueError(
                "DECREASED의 absolute_change는 "
                "0보다 클 수 없습니다."
            )

        object.__setattr__(
            self,
            "field_name",
            normalized_field_name,
        )
        object.__setattr__(
            self,
            "absolute_change",
            normalized_absolute_change,
        )
        object.__setattr__(
            self,
            "percentage_change",
            normalized_percentage_change,
        )

    @property
    def has_changed(self) -> bool:
        """
        실제 변경이 발생했는지 반환한다.
        """
        return self.direction is not ChangeDirection.UNCHANGED

    @property
    def is_numeric_change(self) -> bool:
        """
        숫자 변화량 정보가 존재하는지 반환한다.
        """
        return (
            self.absolute_change is not None
            or self.percentage_change is not None
        )


@dataclass(frozen=True, slots=True)
class ChangeSet:
    """
    동일 상품의 두 Snapshot을 비교한 결과 묶음.

    ChangeSet은 비교 대상의 식별자와 관찰 시점을 보존하고,
    발견된 여러 변화를 하나의 불변 객체로 제공한다.
    """

    previous_snapshot_id: str
    current_snapshot_id: str
    canonical_product_id: str
    marketplace: str
    previous_observed_at: datetime
    current_observed_at: datetime
    changes: tuple[DetectedChange, ...] = field(
        default_factory=tuple
    )
    detected_at: datetime = field(
        default_factory=lambda: datetime.now(
            timezone.utc
        )
    )

    def __post_init__(self) -> None:
        previous_snapshot_id = _normalize_required_text(
            self.previous_snapshot_id,
            field_name="previous_snapshot_id",
        )
        current_snapshot_id = _normalize_required_text(
            self.current_snapshot_id,
            field_name="current_snapshot_id",
        )
        canonical_product_id = _normalize_required_text(
            self.canonical_product_id,
            field_name="canonical_product_id",
        )
        marketplace = _normalize_required_text(
            self.marketplace,
            field_name="marketplace",
        ).lower()

        if previous_snapshot_id == current_snapshot_id:
            raise ValueError(
                "이전 Snapshot과 현재 Snapshot의 ID는 "
                "서로 달라야 합니다."
            )

        _validate_aware_datetime(
            self.previous_observed_at,
            field_name="previous_observed_at",
        )
        _validate_aware_datetime(
            self.current_observed_at,
            field_name="current_observed_at",
        )
        _validate_aware_datetime(
            self.detected_at,
            field_name="detected_at",
        )

        if (
            self.current_observed_at
            < self.previous_observed_at
        ):
            raise ValueError(
                "현재 Snapshot의 관찰 시점은 이전 "
                "Snapshot보다 빠를 수 없습니다."
            )

        normalized_changes = tuple(self.changes)

        if not all(
            isinstance(change, DetectedChange)
            for change in normalized_changes
        ):
            raise TypeError(
                "changes에는 DetectedChange만 "
                "포함할 수 있습니다."
            )

        object.__setattr__(
            self,
            "previous_snapshot_id",
            previous_snapshot_id,
        )
        object.__setattr__(
            self,
            "current_snapshot_id",
            current_snapshot_id,
        )
        object.__setattr__(
            self,
            "canonical_product_id",
            canonical_product_id,
        )
        object.__setattr__(
            self,
            "marketplace",
            marketplace,
        )
        object.__setattr__(
            self,
            "changes",
            normalized_changes,
        )

    @property
    def has_changes(self) -> bool:
        """
        하나 이상의 실제 변화가 있는지 반환한다.
        """
        return any(
            change.has_changed
            for change in self.changes
        )

    @property
    def change_count(self) -> int:
        """
        실제로 변경된 필드 수를 반환한다.
        """
        return sum(
            1
            for change in self.changes
            if change.has_changed
        )

    def changes_of_type(
        self,
        change_type: ChangeType,
    ) -> tuple[DetectedChange, ...]:
        """
        특정 변화 범주에 해당하는 결과만 반환한다.
        """
        if not isinstance(change_type, ChangeType):
            raise TypeError(
                "change_type은 ChangeType이어야 합니다."
            )

        return tuple(
            change
            for change in self.changes
            if change.change_type is change_type
        )