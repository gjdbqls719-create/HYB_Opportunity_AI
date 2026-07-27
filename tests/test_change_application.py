from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.application.change import (
    ChangeDetectionResponse,
    DetectChangesUseCase,
    SnapshotPair,
)
from app.domain.change import (
    ChangeEventType,
)
from market_data.inventory_snapshot import (
    InventorySnapshot,
)
from market_data.price_snapshot import PriceSnapshot
from market_data.seller_snapshot import SellerSnapshot


PREVIOUS_TIME = datetime(
    2026,
    7,
    27,
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
    canonical_product_id: str = "canonical_001",
) -> PriceSnapshot:
    return PriceSnapshot(
        snapshot_id=snapshot_id,
        canonical_product_id=canonical_product_id,
        marketplace="ebay",
        observed_at=observed_at,
        source_url="https://example.com/price",
        item_id="item_001",
        price=price,
        currency="USD",
        condition="new",
        seller_id="seller_001",
    )


def make_inventory_snapshot(
    *,
    snapshot_id: str,
    observed_at: datetime,
    available: bool = True,
    quantity: int | None = 10,
    canonical_product_id: str = "canonical_001",
) -> InventorySnapshot:
    return InventorySnapshot(
        snapshot_id=snapshot_id,
        canonical_product_id=canonical_product_id,
        marketplace="ebay",
        observed_at=observed_at,
        source_url="https://example.com/inventory",
        item_id="item_001",
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
    seller_count: int = 2,
    canonical_product_id: str = "canonical_001",
) -> SellerSnapshot:
    return SellerSnapshot(
        snapshot_id=snapshot_id,
        canonical_product_id=canonical_product_id,
        marketplace="ebay",
        observed_at=observed_at,
        source_url="https://example.com/seller",
        item_id="item_001",
        seller_id=seller_id,
        seller_rating=seller_rating,
        seller_review_count=seller_review_count,
        seller_count=seller_count,
    )


def test_snapshot_pair_accepts_price_snapshots() -> None:
    pair = SnapshotPair(
        previous=make_price_snapshot(
            snapshot_id="price_previous",
            observed_at=PREVIOUS_TIME,
        ),
        current=make_price_snapshot(
            snapshot_id="price_current",
            observed_at=CURRENT_TIME,
        ),
    )

    assert pair.canonical_product_id == "canonical_001"
    assert pair.marketplace == "ebay"
    assert pair.snapshot_type is PriceSnapshot


def test_snapshot_pair_rejects_different_snapshot_types() -> None:
    previous = make_price_snapshot(
        snapshot_id="price_previous",
        observed_at=PREVIOUS_TIME,
    )
    current = make_inventory_snapshot(
        snapshot_id="inventory_current",
        observed_at=CURRENT_TIME,
    )

    with pytest.raises(
        TypeError,
        match="동일한 종류",
    ):
        SnapshotPair(
            previous=previous,
            current=current,
        )


def test_snapshot_pair_is_immutable() -> None:
    pair = SnapshotPair(
        previous=make_price_snapshot(
            snapshot_id="price_previous",
            observed_at=PREVIOUS_TIME,
        ),
        current=make_price_snapshot(
            snapshot_id="price_current",
            observed_at=CURRENT_TIME,
        ),
    )

    with pytest.raises(FrozenInstanceError):
        pair.current = pair.previous  # type: ignore[misc]


def test_use_case_detects_price_change() -> None:
    pair = SnapshotPair(
        previous=make_price_snapshot(
            snapshot_id="price_previous",
            observed_at=PREVIOUS_TIME,
            price=Decimal("100.00"),
        ),
        current=make_price_snapshot(
            snapshot_id="price_current",
            observed_at=CURRENT_TIME,
            price=Decimal("80.00"),
        ),
    )

    response = DetectChangesUseCase().execute(
        snapshot_pairs=(pair,),
    )

    assert response.compared_pair_count == 1
    assert response.changed_pair_count == 1
    assert response.unchanged_pair_count == 0
    assert response.change_count == 1
    assert response.event_count == 1
    assert response.has_changes is True
    assert (
        response.events[0].event_type
        is ChangeEventType.PRICE_DROPPED
    )


def test_use_case_detects_inventory_change() -> None:
    pair = SnapshotPair(
        previous=make_inventory_snapshot(
            snapshot_id="inventory_previous",
            observed_at=PREVIOUS_TIME,
            available=True,
            quantity=10,
        ),
        current=make_inventory_snapshot(
            snapshot_id="inventory_current",
            observed_at=CURRENT_TIME,
            available=False,
            quantity=0,
        ),
    )

    response = DetectChangesUseCase().execute(
        snapshot_pairs=(pair,),
    )

    assert response.changed_pair_count == 1
    assert response.change_count == 2
    assert response.event_count == 2
    assert (
        response.events[0].event_type
        is ChangeEventType.INVENTORY_OUT_OF_STOCK
    )
    assert (
        response.events[1].event_type
        is ChangeEventType
        .INVENTORY_QUANTITY_DECREASED
    )


def test_use_case_detects_seller_change() -> None:
    pair = SnapshotPair(
        previous=make_seller_snapshot(
            snapshot_id="seller_previous",
            observed_at=PREVIOUS_TIME,
            seller_count=2,
        ),
        current=make_seller_snapshot(
            snapshot_id="seller_current",
            observed_at=CURRENT_TIME,
            seller_count=5,
        ),
    )

    response = DetectChangesUseCase().execute(
        snapshot_pairs=(pair,),
    )

    assert response.change_count == 1
    assert (
        response.events[0].event_type
        is ChangeEventType
        .SELLER_COMPETITION_INCREASED
    )


def test_use_case_supports_multiple_snapshot_pairs() -> None:
    price_pair = SnapshotPair(
        previous=make_price_snapshot(
            snapshot_id="price_previous",
            observed_at=PREVIOUS_TIME,
            price=Decimal("100.00"),
        ),
        current=make_price_snapshot(
            snapshot_id="price_current",
            observed_at=CURRENT_TIME,
            price=Decimal("90.00"),
        ),
    )

    inventory_pair = SnapshotPair(
        previous=make_inventory_snapshot(
            snapshot_id="inventory_previous",
            observed_at=PREVIOUS_TIME,
            quantity=10,
        ),
        current=make_inventory_snapshot(
            snapshot_id="inventory_current",
            observed_at=CURRENT_TIME,
            quantity=8,
        ),
    )

    response = DetectChangesUseCase().execute(
        snapshot_pairs=(
            price_pair,
            inventory_pair,
        ),
    )

    assert response.compared_pair_count == 2
    assert response.changed_pair_count == 2
    assert response.change_count == 2
    assert response.event_count == 2


def test_unchanged_pair_produces_no_events() -> None:
    pair = SnapshotPair(
        previous=make_price_snapshot(
            snapshot_id="price_previous",
            observed_at=PREVIOUS_TIME,
        ),
        current=make_price_snapshot(
            snapshot_id="price_current",
            observed_at=CURRENT_TIME,
        ),
    )

    response = DetectChangesUseCase().execute(
        snapshot_pairs=(pair,),
    )

    assert response.compared_pair_count == 1
    assert response.changed_pair_count == 0
    assert response.unchanged_pair_count == 1
    assert response.change_count == 0
    assert response.event_count == 0
    assert response.has_changes is False


def test_empty_input_returns_empty_response() -> None:
    response = DetectChangesUseCase().execute(
        snapshot_pairs=(),
    )

    assert response == ChangeDetectionResponse(
        change_sets=(),
        events=(),
    )
    assert response.compared_pair_count == 0
    assert response.event_count == 0


def test_use_case_rejects_invalid_pair_item() -> None:
    with pytest.raises(
        TypeError,
        match="SnapshotPair",
    ):
        DetectChangesUseCase().execute(
            snapshot_pairs=(
                "invalid",  # type: ignore[arg-type]
            ),
        )


def test_batch_publisher_receives_all_events_once() -> None:
    class RecordingPublisher:
        def __init__(self) -> None:
            self.calls: list[tuple[object, ...]] = []

        def publish_many(
            self,
            events: tuple[object, ...],
        ) -> None:
            self.calls.append(events)

    publisher = RecordingPublisher()

    price_pair = SnapshotPair(
        previous=make_price_snapshot(
            snapshot_id="price_previous",
            observed_at=PREVIOUS_TIME,
            price=Decimal("100.00"),
        ),
        current=make_price_snapshot(
            snapshot_id="price_current",
            observed_at=CURRENT_TIME,
            price=Decimal("90.00"),
        ),
    )

    inventory_pair = SnapshotPair(
        previous=make_inventory_snapshot(
            snapshot_id="inventory_previous",
            observed_at=PREVIOUS_TIME,
            available=True,
        ),
        current=make_inventory_snapshot(
            snapshot_id="inventory_current",
            observed_at=CURRENT_TIME,
            available=False,
        ),
    )

    response = DetectChangesUseCase(
        publisher=publisher,
    ).execute(
        snapshot_pairs=(
            price_pair,
            inventory_pair,
        ),
    )

    assert len(publisher.calls) == 1
    assert publisher.calls[0] == response.events
    assert len(publisher.calls[0]) == 2


def test_publisher_is_not_called_without_events() -> None:
    class RecordingPublisher:
        def __init__(self) -> None:
            self.call_count = 0

        def publish_many(
            self,
            events: tuple[object, ...],
        ) -> None:
            self.call_count += 1

    publisher = RecordingPublisher()

    pair = SnapshotPair(
        previous=make_price_snapshot(
            snapshot_id="price_previous",
            observed_at=PREVIOUS_TIME,
        ),
        current=make_price_snapshot(
            snapshot_id="price_current",
            observed_at=CURRENT_TIME,
        ),
    )

    DetectChangesUseCase(
        publisher=publisher,
    ).execute(
        snapshot_pairs=(pair,),
    )

    assert publisher.call_count == 0


def test_publisher_failure_is_propagated() -> None:
    class FailingPublisher:
        def publish_many(
            self,
            events: tuple[object, ...],
        ) -> None:
            raise RuntimeError("publish failed")

    pair = SnapshotPair(
        previous=make_price_snapshot(
            snapshot_id="price_previous",
            observed_at=PREVIOUS_TIME,
            price=Decimal("100.00"),
        ),
        current=make_price_snapshot(
            snapshot_id="price_current",
            observed_at=CURRENT_TIME,
            price=Decimal("90.00"),
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="publish failed",
    ):
        DetectChangesUseCase(
            publisher=FailingPublisher(),
        ).execute(
            snapshot_pairs=(pair,),
        )


def test_response_filters_events_by_product() -> None:
    first_pair = SnapshotPair(
        previous=make_price_snapshot(
            snapshot_id="first_previous",
            observed_at=PREVIOUS_TIME,
            price=Decimal("100.00"),
            canonical_product_id="canonical_001",
        ),
        current=make_price_snapshot(
            snapshot_id="first_current",
            observed_at=CURRENT_TIME,
            price=Decimal("90.00"),
            canonical_product_id="canonical_001",
        ),
    )

    second_pair = SnapshotPair(
        previous=make_price_snapshot(
            snapshot_id="second_previous",
            observed_at=PREVIOUS_TIME,
            price=Decimal("200.00"),
            canonical_product_id="canonical_002",
        ),
        current=make_price_snapshot(
            snapshot_id="second_current",
            observed_at=CURRENT_TIME,
            price=Decimal("180.00"),
            canonical_product_id="canonical_002",
        ),
    )

    response = DetectChangesUseCase().execute(
        snapshot_pairs=(
            first_pair,
            second_pair,
        ),
    )

    filtered = response.events_for_product(
        "canonical_001"
    )

    assert len(filtered) == 1
    assert (
        filtered[0].canonical_product_id
        == "canonical_001"
    )


def test_response_rejects_blank_product_filter() -> None:
    response = ChangeDetectionResponse(
        change_sets=(),
        events=(),
    )

    with pytest.raises(
        ValueError,
        match="canonical_product_id",
    ):
        response.events_for_product(" ")