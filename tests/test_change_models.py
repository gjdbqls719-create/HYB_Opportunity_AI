from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domain.change import (
    ChangeDirection,
    ChangeSet,
    ChangeType,
    DetectedChange,
)


PREVIOUS_OBSERVED_AT = datetime(
    2026,
    7,
    26,
    10,
    0,
    tzinfo=timezone.utc,
)

CURRENT_OBSERVED_AT = datetime(
    2026,
    7,
    26,
    11,
    0,
    tzinfo=timezone.utc,
)


def make_change_set(
    *,
    changes: tuple[DetectedChange, ...] = (),
) -> ChangeSet:
    return ChangeSet(
        previous_snapshot_id="price_previous",
        current_snapshot_id="price_current",
        canonical_product_id="canonical_001",
        marketplace="EBAY",
        previous_observed_at=PREVIOUS_OBSERVED_AT,
        current_observed_at=CURRENT_OBSERVED_AT,
        changes=changes,
    )


def test_detected_change_creates_price_decrease() -> None:
    change = DetectedChange(
        change_type=ChangeType.PRICE,
        field_name="price",
        previous_value=Decimal("100.00"),
        current_value=Decimal("90.00"),
        direction=ChangeDirection.DECREASED,
        absolute_change=Decimal("-10.00"),
        percentage_change=Decimal("-10.00"),
    )

    assert change.change_type is ChangeType.PRICE
    assert change.field_name == "price"
    assert change.previous_value == Decimal("100.00")
    assert change.current_value == Decimal("90.00")
    assert change.direction is ChangeDirection.DECREASED
    assert change.absolute_change == Decimal("-10.00")
    assert change.percentage_change == Decimal("-10.00")
    assert change.has_changed is True
    assert change.is_numeric_change is True


def test_detected_change_normalizes_field_name() -> None:
    change = DetectedChange(
        change_type=ChangeType.INVENTORY,
        field_name="  quantity  ",
        previous_value=10,
        current_value=5,
        direction=ChangeDirection.DECREASED,
        absolute_change=-5,
    )

    assert change.field_name == "quantity"
    assert change.absolute_change == Decimal("-5")


def test_detected_change_accepts_non_numeric_change() -> None:
    change = DetectedChange(
        change_type=ChangeType.SELLER,
        field_name="seller_id",
        previous_value="seller_a",
        current_value="seller_b",
        direction=ChangeDirection.CHANGED,
    )

    assert change.has_changed is True
    assert change.is_numeric_change is False


def test_detected_change_represents_unchanged_value() -> None:
    change = DetectedChange(
        change_type=ChangeType.INVENTORY,
        field_name="available",
        previous_value=True,
        current_value=True,
        direction=ChangeDirection.UNCHANGED,
    )

    assert change.has_changed is False


def test_detected_change_rejects_empty_field_name() -> None:
    with pytest.raises(
        ValueError,
        match="field_name은 비어 있을 수 없습니다",
    ):
        DetectedChange(
            change_type=ChangeType.PRICE,
            field_name=" ",
            previous_value=100,
            current_value=90,
            direction=ChangeDirection.DECREASED,
        )


def test_detected_change_rejects_invalid_change_type() -> None:
    with pytest.raises(
        TypeError,
        match="change_type은 ChangeType이어야 합니다",
    ):
        DetectedChange(
            change_type="price",  # type: ignore[arg-type]
            field_name="price",
            previous_value=100,
            current_value=90,
            direction=ChangeDirection.DECREASED,
        )


def test_detected_change_rejects_invalid_direction() -> None:
    with pytest.raises(
        TypeError,
        match="direction은 ChangeDirection이어야 합니다",
    ):
        DetectedChange(
            change_type=ChangeType.PRICE,
            field_name="price",
            previous_value=100,
            current_value=90,
            direction="decreased",  # type: ignore[arg-type]
        )


def test_unchanged_direction_requires_equal_values() -> None:
    with pytest.raises(
        ValueError,
        match="이전 값과 현재 값이 같아야 합니다",
    ):
        DetectedChange(
            change_type=ChangeType.PRICE,
            field_name="price",
            previous_value=100,
            current_value=90,
            direction=ChangeDirection.UNCHANGED,
        )


def test_changed_direction_requires_different_values() -> None:
    with pytest.raises(
        ValueError,
        match="이전 값과 현재 값이 달라야 합니다",
    ):
        DetectedChange(
            change_type=ChangeType.PRICE,
            field_name="price",
            previous_value=100,
            current_value=100,
            direction=ChangeDirection.DECREASED,
        )


def test_increased_change_rejects_negative_absolute_change() -> None:
    with pytest.raises(
        ValueError,
        match="0보다 작을 수 없습니다",
    ):
        DetectedChange(
            change_type=ChangeType.PRICE,
            field_name="price",
            previous_value=90,
            current_value=100,
            direction=ChangeDirection.INCREASED,
            absolute_change=-10,
        )


def test_decreased_change_rejects_positive_absolute_change() -> None:
    with pytest.raises(
        ValueError,
        match="0보다 클 수 없습니다",
    ):
        DetectedChange(
            change_type=ChangeType.PRICE,
            field_name="price",
            previous_value=100,
            current_value=90,
            direction=ChangeDirection.DECREASED,
            absolute_change=10,
        )


def test_detected_change_is_immutable() -> None:
    change = DetectedChange(
        change_type=ChangeType.PRICE,
        field_name="price",
        previous_value=100,
        current_value=90,
        direction=ChangeDirection.DECREASED,
    )

    with pytest.raises(FrozenInstanceError):
        change.field_name = "currency"  # type: ignore[misc]


def test_change_set_creates_empty_result() -> None:
    change_set = make_change_set()

    assert change_set.marketplace == "ebay"
    assert change_set.changes == ()
    assert change_set.has_changes is False
    assert change_set.change_count == 0


def test_change_set_collects_multiple_changes() -> None:
    price_change = DetectedChange(
        change_type=ChangeType.PRICE,
        field_name="price",
        previous_value=Decimal("100.00"),
        current_value=Decimal("90.00"),
        direction=ChangeDirection.DECREASED,
        absolute_change=Decimal("-10.00"),
    )

    inventory_change = DetectedChange(
        change_type=ChangeType.INVENTORY,
        field_name="available",
        previous_value=True,
        current_value=False,
        direction=ChangeDirection.CHANGED,
    )

    change_set = make_change_set(
        changes=(
            price_change,
            inventory_change,
        )
    )

    assert change_set.has_changes is True
    assert change_set.change_count == 2
    assert change_set.changes_of_type(
        ChangeType.PRICE
    ) == (price_change,)
    assert change_set.changes_of_type(
        ChangeType.INVENTORY
    ) == (inventory_change,)
    assert change_set.changes_of_type(
        ChangeType.SELLER
    ) == ()


def test_change_set_converts_changes_to_tuple() -> None:
    change = DetectedChange(
        change_type=ChangeType.SELLER,
        field_name="seller_count",
        previous_value=2,
        current_value=4,
        direction=ChangeDirection.INCREASED,
        absolute_change=2,
    )

    change_set = ChangeSet(
        previous_snapshot_id="seller_previous",
        current_snapshot_id="seller_current",
        canonical_product_id="canonical_001",
        marketplace="amazon",
        previous_observed_at=PREVIOUS_OBSERVED_AT,
        current_observed_at=CURRENT_OBSERVED_AT,
        changes=[change],  # type: ignore[arg-type]
    )

    assert change_set.changes == (change,)
    assert isinstance(change_set.changes, tuple)


def test_change_set_rejects_same_snapshot_ids() -> None:
    with pytest.raises(
        ValueError,
        match="ID는 서로 달라야 합니다",
    ):
        ChangeSet(
            previous_snapshot_id="same_snapshot",
            current_snapshot_id="same_snapshot",
            canonical_product_id="canonical_001",
            marketplace="ebay",
            previous_observed_at=PREVIOUS_OBSERVED_AT,
            current_observed_at=CURRENT_OBSERVED_AT,
        )


def test_change_set_rejects_current_time_before_previous_time() -> None:
    with pytest.raises(
        ValueError,
        match="관찰 시점은 이전 Snapshot보다 빠를 수 없습니다",
    ):
        ChangeSet(
            previous_snapshot_id="previous",
            current_snapshot_id="current",
            canonical_product_id="canonical_001",
            marketplace="ebay",
            previous_observed_at=CURRENT_OBSERVED_AT,
            current_observed_at=PREVIOUS_OBSERVED_AT,
        )


@pytest.mark.parametrize(
    "field_name",
    [
        "previous_observed_at",
        "current_observed_at",
        "detected_at",
    ],
)
def test_change_set_requires_timezone_aware_datetimes(
    field_name: str,
) -> None:
    arguments = {
        "previous_snapshot_id": "previous",
        "current_snapshot_id": "current",
        "canonical_product_id": "canonical_001",
        "marketplace": "ebay",
        "previous_observed_at": PREVIOUS_OBSERVED_AT,
        "current_observed_at": CURRENT_OBSERVED_AT,
        "detected_at": CURRENT_OBSERVED_AT
        + timedelta(minutes=1),
    }

    arguments[field_name] = datetime(
        2026,
        7,
        26,
        12,
        0,
    )

    with pytest.raises(
        ValueError,
        match="timezone 정보가 필요합니다",
    ):
        ChangeSet(**arguments)


def test_change_set_rejects_non_change_items() -> None:
    with pytest.raises(
        TypeError,
        match="DetectedChange만 포함할 수 있습니다",
    ):
        ChangeSet(
            previous_snapshot_id="previous",
            current_snapshot_id="current",
            canonical_product_id="canonical_001",
            marketplace="ebay",
            previous_observed_at=PREVIOUS_OBSERVED_AT,
            current_observed_at=CURRENT_OBSERVED_AT,
            changes=("invalid",),  # type: ignore[arg-type]
        )


def test_change_set_is_immutable() -> None:
    change_set = make_change_set()

    with pytest.raises(FrozenInstanceError):
        change_set.marketplace = "amazon"  # type: ignore[misc]