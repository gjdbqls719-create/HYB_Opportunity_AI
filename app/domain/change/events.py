from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping
from uuid import uuid4

from app.domain.change.models import (
    ChangeDirection,
    ChangeType,
)


class ChangeEventType(str, Enum):
    """
    Change Domain에서 외부로 전달하는 이벤트 종류.

    이벤트 이름은 단순 필드 변경이 아니라
    비즈니스적으로 해석 가능한 의미를 표현한다.
    """

    PRICE_DROPPED = "price_dropped"
    PRICE_INCREASED = "price_increased"
    PRICE_CONDITION_CHANGED = (
        "price_condition_changed"
    )
    PRICE_SELLER_CHANGED = "price_seller_changed"

    INVENTORY_OUT_OF_STOCK = (
        "inventory_out_of_stock"
    )
    INVENTORY_RESTOCKED = "inventory_restocked"
    INVENTORY_QUANTITY_INCREASED = (
        "inventory_quantity_increased"
    )
    INVENTORY_QUANTITY_DECREASED = (
        "inventory_quantity_decreased"
    )
    INVENTORY_QUANTITY_CHANGED = (
        "inventory_quantity_changed"
    )

    SELLER_CHANGED = "seller_changed"
    SELLER_RATING_INCREASED = (
        "seller_rating_increased"
    )
    SELLER_RATING_DECREASED = (
        "seller_rating_decreased"
    )
    SELLER_RATING_CHANGED = (
        "seller_rating_changed"
    )
    SELLER_REVIEW_COUNT_INCREASED = (
        "seller_review_count_increased"
    )
    SELLER_REVIEW_COUNT_DECREASED = (
        "seller_review_count_decreased"
    )
    SELLER_REVIEW_COUNT_CHANGED = (
        "seller_review_count_changed"
    )
    SELLER_COMPETITION_INCREASED = (
        "seller_competition_increased"
    )
    SELLER_COMPETITION_DECREASED = (
        "seller_competition_decreased"
    )

    CHANGE_DETECTED = "change_detected"


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
            f"{field_name}은 유효한 timezone 정보가 "
            "필요합니다."
        )


@dataclass(frozen=True, slots=True)
class ChangeDetectedEvent:
    """
    ChangeSet에서 파생된 불변 도메인 이벤트.

    이벤트는 변화가 발생한 상품과 Snapshot,
    변경 필드, 이전 값과 현재 값을 보존한다.

    알림, 저장소, Workflow 등의 외부 계층은
    ChangeSet 내부 구조를 직접 해석하지 않고
    이 이벤트만 받아 처리할 수 있다.
    """

    event_type: ChangeEventType
    change_type: ChangeType
    direction: ChangeDirection

    canonical_product_id: str
    marketplace: str

    previous_snapshot_id: str
    current_snapshot_id: str

    field_name: str
    previous_value: Any
    current_value: Any

    previous_observed_at: datetime
    current_observed_at: datetime

    absolute_change: Decimal | None = None
    percentage_change: Decimal | None = None

    event_id: str = field(
        default_factory=lambda: str(uuid4())
    )
    occurred_at: datetime = field(
        default_factory=lambda: datetime.now(
            timezone.utc
        )
    )
    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        if not isinstance(
            self.event_type,
            ChangeEventType,
        ):
            raise TypeError(
                "event_type은 ChangeEventType이어야 합니다."
            )

        if not isinstance(
            self.change_type,
            ChangeType,
        ):
            raise TypeError(
                "change_type은 ChangeType이어야 합니다."
            )

        if not isinstance(
            self.direction,
            ChangeDirection,
        ):
            raise TypeError(
                "direction은 ChangeDirection이어야 합니다."
            )

        event_id = _normalize_required_text(
            self.event_id,
            field_name="event_id",
        )
        canonical_product_id = (
            _normalize_required_text(
                self.canonical_product_id,
                field_name="canonical_product_id",
            )
        )
        marketplace = _normalize_required_text(
            self.marketplace,
            field_name="marketplace",
        ).lower()
        previous_snapshot_id = (
            _normalize_required_text(
                self.previous_snapshot_id,
                field_name="previous_snapshot_id",
            )
        )
        current_snapshot_id = (
            _normalize_required_text(
                self.current_snapshot_id,
                field_name="current_snapshot_id",
            )
        )
        field_name = _normalize_required_text(
            self.field_name,
            field_name="field_name",
        )

        if (
            previous_snapshot_id
            == current_snapshot_id
        ):
            raise ValueError(
                "이전 Snapshot과 현재 Snapshot의 ID는 "
                "서로 달라야 합니다."
            )

        if (
            self.direction
            is ChangeDirection.UNCHANGED
        ):
            raise ValueError(
                "변화 이벤트는 UNCHANGED 방향을 "
                "가질 수 없습니다."
            )

        if self.previous_value == self.current_value:
            raise ValueError(
                "변화 이벤트의 이전 값과 현재 값은 "
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
            self.occurred_at,
            field_name="occurred_at",
        )

        if (
            self.current_observed_at
            < self.previous_observed_at
        ):
            raise ValueError(
                "현재 Snapshot의 관찰 시점은 이전 "
                "Snapshot보다 빠를 수 없습니다."
            )

        object.__setattr__(
            self,
            "event_id",
            event_id,
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
            "field_name",
            field_name,
        )
        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(
                dict(self.metadata)
            ),
        )

    @property
    def identity_key(self) -> str:
        """
        이벤트 대상 상품의 기본 식별 키.
        """
        return (
            f"{self.marketplace}:"
            f"{self.canonical_product_id}"
        )

    @property
    def is_price_event(self) -> bool:
        return self.change_type is ChangeType.PRICE

    @property
    def is_inventory_event(self) -> bool:
        return (
            self.change_type
            is ChangeType.INVENTORY
        )

    @property
    def is_seller_event(self) -> bool:
        return self.change_type is ChangeType.SELLER