from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.domain.change.models import (
    ChangeDirection,
    ChangeSet,
    ChangeType,
    DetectedChange,
)
from market_data.inventory_snapshot import InventorySnapshot
from market_data.price_snapshot import PriceSnapshot
from market_data.seller_snapshot import SellerSnapshot


def detect_price_changes(
    previous: PriceSnapshot,
    current: PriceSnapshot,
) -> ChangeSet:
    """
    두 PriceSnapshot을 비교해 가격 관련 변화를 반환한다.
    """
    _validate_snapshot_pair(
        previous=previous,
        current=current,
    )

    if previous.currency != current.currency:
        raise ValueError(
            "서로 다른 통화의 PriceSnapshot은 "
            "직접 비교할 수 없습니다."
        )

    changes: list[DetectedChange] = []

    price_change = _build_numeric_change(
        change_type=ChangeType.PRICE,
        field_name="price",
        previous_value=previous.price,
        current_value=current.price,
        include_percentage=True,
    )

    if price_change is not None:
        changes.append(price_change)

    condition_change = _build_value_change(
        change_type=ChangeType.PRICE,
        field_name="condition",
        previous_value=previous.condition,
        current_value=current.condition,
    )

    if condition_change is not None:
        changes.append(condition_change)

    seller_id_change = _build_value_change(
        change_type=ChangeType.PRICE,
        field_name="seller_id",
        previous_value=previous.seller_id,
        current_value=current.seller_id,
    )

    if seller_id_change is not None:
        changes.append(seller_id_change)

    return _build_change_set(
        previous=previous,
        current=current,
        changes=changes,
    )


def detect_inventory_changes(
    previous: InventorySnapshot,
    current: InventorySnapshot,
) -> ChangeSet:
    """
    두 InventorySnapshot을 비교해 재고 변화를 반환한다.
    """
    _validate_snapshot_pair(
        previous=previous,
        current=current,
    )

    changes: list[DetectedChange] = []

    availability_change = _build_value_change(
        change_type=ChangeType.INVENTORY,
        field_name="available",
        previous_value=previous.available,
        current_value=current.available,
    )

    if availability_change is not None:
        changes.append(availability_change)

    quantity_change = _build_optional_numeric_change(
        change_type=ChangeType.INVENTORY,
        field_name="quantity",
        previous_value=previous.quantity,
        current_value=current.quantity,
    )

    if quantity_change is not None:
        changes.append(quantity_change)

    return _build_change_set(
        previous=previous,
        current=current,
        changes=changes,
    )


def detect_seller_changes(
    previous: SellerSnapshot,
    current: SellerSnapshot,
) -> ChangeSet:
    """
    두 SellerSnapshot을 비교해 판매자 관련 변화를 반환한다.
    """
    _validate_snapshot_pair(
        previous=previous,
        current=current,
    )

    changes: list[DetectedChange] = []

    seller_id_change = _build_value_change(
        change_type=ChangeType.SELLER,
        field_name="seller_id",
        previous_value=previous.seller_id,
        current_value=current.seller_id,
    )

    if seller_id_change is not None:
        changes.append(seller_id_change)

    seller_rating_change = _build_optional_numeric_change(
        change_type=ChangeType.SELLER,
        field_name="seller_rating",
        previous_value=previous.seller_rating,
        current_value=current.seller_rating,
    )

    if seller_rating_change is not None:
        changes.append(seller_rating_change)

    seller_review_count_change = (
        _build_optional_numeric_change(
            change_type=ChangeType.SELLER,
            field_name="seller_review_count",
            previous_value=previous.seller_review_count,
            current_value=current.seller_review_count,
        )
    )

    if seller_review_count_change is not None:
        changes.append(seller_review_count_change)

    seller_count_change = _build_numeric_change(
        change_type=ChangeType.SELLER,
        field_name="seller_count",
        previous_value=previous.seller_count,
        current_value=current.seller_count,
    )

    if seller_count_change is not None:
        changes.append(seller_count_change)

    return _build_change_set(
        previous=previous,
        current=current,
        changes=changes,
    )


def _validate_snapshot_pair(
    *,
    previous: Any,
    current: Any,
) -> None:
    """
    두 Snapshot이 동일 상품을 나타내는지 검증한다.
    """
    if previous.snapshot_id == current.snapshot_id:
        raise ValueError(
            "이전 Snapshot과 현재 Snapshot의 ID는 "
            "서로 달라야 합니다."
        )

    if (
        previous.canonical_product_id
        != current.canonical_product_id
    ):
        raise ValueError(
            "서로 다른 canonical product의 Snapshot은 "
            "비교할 수 없습니다."
        )

    if previous.marketplace != current.marketplace:
        raise ValueError(
            "서로 다른 Marketplace의 Snapshot은 "
            "비교할 수 없습니다."
        )

    if previous.item_id != current.item_id:
        raise ValueError(
            "서로 다른 item의 Snapshot은 "
            "비교할 수 없습니다."
        )

    if current.observed_at < previous.observed_at:
        raise ValueError(
            "현재 Snapshot의 관찰 시점은 이전 "
            "Snapshot보다 빠를 수 없습니다."
        )


def _build_value_change(
    *,
    change_type: ChangeType,
    field_name: str,
    previous_value: Any,
    current_value: Any,
) -> DetectedChange | None:
    """
    방향성이 없는 일반 값의 변화를 생성한다.
    """
    if previous_value == current_value:
        return None

    return DetectedChange(
        change_type=change_type,
        field_name=field_name,
        previous_value=previous_value,
        current_value=current_value,
        direction=ChangeDirection.CHANGED,
    )


def _build_optional_numeric_change(
    *,
    change_type: ChangeType,
    field_name: str,
    previous_value: Any,
    current_value: Any,
) -> DetectedChange | None:
    """
    None을 허용하는 숫자 필드의 변화를 생성한다.

    한쪽 값이 None이면 정확한 증감 계산이 불가능하므로
    CHANGED 방향으로 처리한다.
    """
    if previous_value == current_value:
        return None

    if previous_value is None or current_value is None:
        return DetectedChange(
            change_type=change_type,
            field_name=field_name,
            previous_value=previous_value,
            current_value=current_value,
            direction=ChangeDirection.CHANGED,
        )

    return _build_numeric_change(
        change_type=change_type,
        field_name=field_name,
        previous_value=previous_value,
        current_value=current_value,
    )


def _build_numeric_change(
    *,
    change_type: ChangeType,
    field_name: str,
    previous_value: Any,
    current_value: Any,
    include_percentage: bool = False,
) -> DetectedChange | None:
    """
    숫자형 필드의 증감 변화를 생성한다.
    """
    if previous_value == current_value:
        return None

    previous_decimal = Decimal(str(previous_value))
    current_decimal = Decimal(str(current_value))

    absolute_change = current_decimal - previous_decimal

    if absolute_change > 0:
        direction = ChangeDirection.INCREASED
    else:
        direction = ChangeDirection.DECREASED

    percentage_change: Decimal | None = None

    if include_percentage and previous_decimal != 0:
        percentage_change = (
            absolute_change
            / previous_decimal
            * Decimal("100")
        )

    return DetectedChange(
        change_type=change_type,
        field_name=field_name,
        previous_value=previous_value,
        current_value=current_value,
        direction=direction,
        absolute_change=absolute_change,
        percentage_change=percentage_change,
    )


def _build_change_set(
    *,
    previous: Any,
    current: Any,
    changes: list[DetectedChange],
) -> ChangeSet:
    """
    비교 결과를 표준 ChangeSet으로 변환한다.
    """
    return ChangeSet(
        previous_snapshot_id=previous.snapshot_id,
        current_snapshot_id=current.snapshot_id,
        canonical_product_id=(
            current.canonical_product_id
        ),
        marketplace=current.marketplace,
        previous_observed_at=previous.observed_at,
        current_observed_at=current.observed_at,
        changes=tuple(changes),
    )