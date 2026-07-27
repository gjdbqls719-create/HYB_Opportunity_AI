from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domain.change import (
    ChangeDirection,
    ChangeType,
    detect_inventory_changes,
    detect_price_changes,
    detect_seller_changes,
)
from market_data.inventory_snapshot import InventorySnapshot
from market_data.price_snapshot import PriceSnapshot
from market_data.seller_snapshot import SellerSnapshot


PREVIOUS_TIME = datetime(
    2026,
    7,
    26,
    10,
    0,
    tzinfo=timezone.utc,
)

CURRENT_TIME = PREVIOUS_TIME + timedelta(hours=1)


def make_price_snapshot(
    *,
    snapshot_id: str,
    observed_at: datetime,
    price: Decimal = Decimal("100.00"),
    currency: str = "USD",
    condition: str = "new",
    seller_id: str | None = "seller_001",
    canonical_product_id: str = "canonical_001",
    marketplace: str = "ebay",
    item_id: str = "item_001",
) -> PriceSnapshot:
    return PriceSnapshot(
        snapshot_id=snapshot_id,
        canonical_product_id=canonical_product_id,
        marketplace=marketplace,
        observed_at=observed_at,
        source_url="https://example.com/item",
        item_id=item_id,
        price=price,
        currency=currency,
        condition=condition,
        seller_id=seller_id,
    )


def make_inventory_snapshot(
    *,
    snapshot_id: str,
    observed_at: datetime,
    available: bool = True,
    quantity: int | None = 10,
    canonical_product_id: str = "canonical_001",
    marketplace: str = "ebay",
    item_id: str = "item_001",
) -> InventorySnapshot:
    return InventorySnapshot(
        snapshot_id=snapshot_id,
        canonical_product_id=canonical_product_id,
        marketplace=marketplace,
        observed_at=observed_at,
        source_url="https://example.com/item",
        item_id=item_id,
        available=available,
        quantity=quantity,
    )


def make_seller_snapshot(
    *,
    snapshot_id: str,
    observed_at: datetime,
    seller_id: str | None = "seller_001",
    seller_rating: float | None = 4.5,
    seller_review_count: int | None = 100,
    seller_count: int = 3,
    canonical_product_id: str = "canonical_001",
    marketplace: str = "ebay",
    item_id: str = "item_001",
) -> SellerSnapshot:
    return SellerSnapshot(
        snapshot_id=snapshot_id,
        canonical_product_id=canonical_product_id,
        marketplace=marketplace,
        observed_at=observed_at,
        source_url="https://example.com/item",
        item_id=item_id,
        seller_id=seller_id,
        seller_rating=seller_rating,
        seller_review_count=seller_review_count,
        seller_count=seller_count,
    )


def test_detect_price_decrease() -> None:
    previous = make_price_snapshot(
        snapshot_id="price_previous",
        observed_at=PREVIOUS_TIME,
        price=Decimal("100.00"),
    )
    current = make_price_snapshot(
        snapshot_id="price_current",
        observed_at=CURRENT_TIME,
        price=Decimal("90.00"),
    )

    result = detect_price_changes(
        previous,
        current,
    )

    assert result.has_changes is True
    assert result.change_count == 1

    change = result.changes[0]

    assert change.change_type is ChangeType.PRICE
    assert change.field_name == "price"
    assert change.direction is ChangeDirection.DECREASED
    assert change.absolute_change == Decimal("-10.00")
    assert change.percentage_change == Decimal("-10.0")


def test_detect_price_increase() -> None:
    previous = make_price_snapshot(
        snapshot_id="price_previous",
        observed_at=PREVIOUS_TIME,
        price=Decimal("80.00"),
    )
    current = make_price_snapshot(
        snapshot_id="price_current",
        observed_at=CURRENT_TIME,
        price=Decimal("100.00"),
    )

    result = detect_price_changes(
        previous,
        current,
    )

    change = result.changes[0]

    assert change.direction is ChangeDirection.INCREASED
    assert change.absolute_change == Decimal("20.00")
    assert change.percentage_change == Decimal("25.00")


def test_price_percentage_is_none_when_previous_price_is_zero() -> None:
    previous = make_price_snapshot(
        snapshot_id="price_previous",
        observed_at=PREVIOUS_TIME,
        price=Decimal("0"),
    )
    current = make_price_snapshot(
        snapshot_id="price_current",
        observed_at=CURRENT_TIME,
        price=Decimal("10"),
    )

    result = detect_price_changes(
        previous,
        current,
    )

    assert result.changes[0].percentage_change is None


def test_detect_price_metadata_changes() -> None:
    previous = make_price_snapshot(
        snapshot_id="price_previous",
        observed_at=PREVIOUS_TIME,
        condition="used",
        seller_id="seller_a",
    )
    current = make_price_snapshot(
        snapshot_id="price_current",
        observed_at=CURRENT_TIME,
        condition="new",
        seller_id="seller_b",
    )

    result = detect_price_changes(
        previous,
        current,
    )

    assert result.change_count == 2

    fields = {
        change.field_name
        for change in result.changes
    }

    assert fields == {
        "condition",
        "seller_id",
    }


def test_identical_price_snapshots_have_no_changes() -> None:
    previous = make_price_snapshot(
        snapshot_id="price_previous",
        observed_at=PREVIOUS_TIME,
    )
    current = make_price_snapshot(
        snapshot_id="price_current",
        observed_at=CURRENT_TIME,
    )

    result = detect_price_changes(
        previous,
        current,
    )

    assert result.has_changes is False
    assert result.changes == ()


def test_price_detector_rejects_different_currencies() -> None:
    previous = make_price_snapshot(
        snapshot_id="price_previous",
        observed_at=PREVIOUS_TIME,
        currency="USD",
    )
    current = make_price_snapshot(
        snapshot_id="price_current",
        observed_at=CURRENT_TIME,
        currency="KRW",
    )

    with pytest.raises(
        ValueError,
        match="서로 다른 통화",
    ):
        detect_price_changes(
            previous,
            current,
        )


def test_detect_inventory_availability_change() -> None:
    previous = make_inventory_snapshot(
        snapshot_id="inventory_previous",
        observed_at=PREVIOUS_TIME,
        available=True,
    )
    current = make_inventory_snapshot(
        snapshot_id="inventory_current",
        observed_at=CURRENT_TIME,
        available=False,
    )

    result = detect_inventory_changes(
        previous,
        current,
    )

    change = result.changes[0]

    assert change.field_name == "available"
    assert change.direction is ChangeDirection.CHANGED


def test_detect_inventory_quantity_decrease() -> None:
    previous = make_inventory_snapshot(
        snapshot_id="inventory_previous",
        observed_at=PREVIOUS_TIME,
        quantity=10,
    )
    current = make_inventory_snapshot(
        snapshot_id="inventory_current",
        observed_at=CURRENT_TIME,
        quantity=4,
    )

    result = detect_inventory_changes(
        previous,
        current,
    )

    change = result.changes[0]

    assert change.field_name == "quantity"
    assert change.direction is ChangeDirection.DECREASED
    assert change.absolute_change == Decimal("-6")


def test_inventory_quantity_none_transition_is_changed() -> None:
    previous = make_inventory_snapshot(
        snapshot_id="inventory_previous",
        observed_at=PREVIOUS_TIME,
        quantity=None,
    )
    current = make_inventory_snapshot(
        snapshot_id="inventory_current",
        observed_at=CURRENT_TIME,
        quantity=5,
    )

    result = detect_inventory_changes(
        previous,
        current,
    )

    change = result.changes[0]

    assert change.direction is ChangeDirection.CHANGED
    assert change.absolute_change is None


def test_detect_seller_changes() -> None:
    previous = make_seller_snapshot(
        snapshot_id="seller_previous",
        observed_at=PREVIOUS_TIME,
        seller_id="seller_a",
        seller_rating=4.8,
        seller_review_count=100,
        seller_count=2,
    )
    current = make_seller_snapshot(
        snapshot_id="seller_current",
        observed_at=CURRENT_TIME,
        seller_id="seller_b",
        seller_rating=4.2,
        seller_review_count=120,
        seller_count=5,
    )

    result = detect_seller_changes(
        previous,
        current,
    )

    assert result.change_count == 4

    changes = {
        change.field_name: change
        for change in result.changes
    }

    assert (
        changes["seller_id"].direction
        is ChangeDirection.CHANGED
    )
    assert (
        changes["seller_rating"].direction
        is ChangeDirection.DECREASED
    )
    assert (
        changes["seller_review_count"].direction
        is ChangeDirection.INCREASED
    )
    assert (
        changes["seller_count"].direction
        is ChangeDirection.INCREASED
    )


def test_seller_optional_value_transition_is_changed() -> None:
    previous = make_seller_snapshot(
        snapshot_id="seller_previous",
        observed_at=PREVIOUS_TIME,
        seller_rating=None,
    )
    current = make_seller_snapshot(
        snapshot_id="seller_current",
        observed_at=CURRENT_TIME,
        seller_rating=4.5,
    )

    result = detect_seller_changes(
        previous,
        current,
    )

    change = result.changes[0]

    assert change.field_name == "seller_rating"
    assert change.direction is ChangeDirection.CHANGED


@pytest.mark.parametrize(
    (
        "changed_field",
        "changed_value",
        "expected_message",
    ),
    [
        (
            "canonical_product_id",
            "canonical_002",
            "서로 다른 canonical product",
        ),
        (
            "marketplace",
            "amazon",
            "서로 다른 Marketplace",
        ),
        (
            "item_id",
            "item_002",
            "서로 다른 item",
        ),
    ],
)
def test_detector_rejects_different_snapshot_identity(
    changed_field: str,
    changed_value: str,
    expected_message: str,
) -> None:
    previous = make_price_snapshot(
        snapshot_id="price_previous",
        observed_at=PREVIOUS_TIME,
    )

    arguments = {
        "snapshot_id": "price_current",
        "observed_at": CURRENT_TIME,
        "canonical_product_id": "canonical_001",
        "marketplace": "ebay",
        "item_id": "item_001",
    }

    arguments[changed_field] = changed_value

    current = make_price_snapshot(**arguments)

    with pytest.raises(
        ValueError,
        match=expected_message,
    ):
        detect_price_changes(
            previous,
            current,
        )


def test_detector_rejects_reverse_observation_order() -> None:
    previous = make_inventory_snapshot(
        snapshot_id="inventory_previous",
        observed_at=CURRENT_TIME,
    )
    current = make_inventory_snapshot(
        snapshot_id="inventory_current",
        observed_at=PREVIOUS_TIME,
    )

    with pytest.raises(
        ValueError,
        match="관찰 시점",
    ):
        detect_inventory_changes(
            previous,
            current,
        )


def test_detector_rejects_same_snapshot_id() -> None:
    previous = make_seller_snapshot(
        snapshot_id="same_snapshot",
        observed_at=PREVIOUS_TIME,
    )
    current = make_seller_snapshot(
        snapshot_id="same_snapshot",
        observed_at=CURRENT_TIME,
    )

    with pytest.raises(
        ValueError,
        match="ID는 서로 달라야 합니다",
    ):
        detect_seller_changes(
            previous,
            current,
        )