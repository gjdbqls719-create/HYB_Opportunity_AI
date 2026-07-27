from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal
from types import MappingProxyType

import pytest

from app.domain.change import (
    ChangeDetectedEvent,
    ChangeDirection,
    ChangeEventBatchPublisher,
    ChangeEventPublisher,
    ChangeEventType,
    ChangeSet,
    ChangeType,
    DetectedChange,
    create_change_events,
)


PREVIOUS_TIME = datetime(
    2026,
    7,
    26,
    10,
    0,
    tzinfo=timezone.utc,
)

CURRENT_TIME = datetime(
    2026,
    7,
    26,
    11,
    0,
    tzinfo=timezone.utc,
)


def make_change_set(
    *changes: DetectedChange,
) -> ChangeSet:
    return ChangeSet(
        previous_snapshot_id="previous_snapshot",
        current_snapshot_id="current_snapshot",
        canonical_product_id="canonical_001",
        marketplace="EBAY",
        previous_observed_at=PREVIOUS_TIME,
        current_observed_at=CURRENT_TIME,
        changes=changes,
    )


def test_create_price_dropped_event() -> None:
    change = DetectedChange(
        change_type=ChangeType.PRICE,
        field_name="price",
        previous_value=Decimal("100.00"),
        current_value=Decimal("90.00"),
        direction=ChangeDirection.DECREASED,
        absolute_change=Decimal("-10.00"),
        percentage_change=Decimal("-10.00"),
    )

    events = create_change_events(
        make_change_set(change)
    )

    assert len(events) == 1

    event = events[0]

    assert (
        event.event_type
        is ChangeEventType.PRICE_DROPPED
    )
    assert event.change_type is ChangeType.PRICE
    assert (
        event.direction
        is ChangeDirection.DECREASED
    )
    assert event.absolute_change == Decimal("-10.00")
    assert (
        event.percentage_change
        == Decimal("-10.00")
    )
    assert event.marketplace == "ebay"
    assert (
        event.identity_key
        == "ebay:canonical_001"
    )
    assert event.is_price_event is True
    assert event.is_inventory_event is False
    assert event.is_seller_event is False


def test_create_price_increased_event() -> None:
    change = DetectedChange(
        change_type=ChangeType.PRICE,
        field_name="price",
        previous_value=Decimal("90.00"),
        current_value=Decimal("100.00"),
        direction=ChangeDirection.INCREASED,
        absolute_change=Decimal("10.00"),
    )

    event = create_change_events(
        make_change_set(change)
    )[0]

    assert (
        event.event_type
        is ChangeEventType.PRICE_INCREASED
    )


@pytest.mark.parametrize(
    (
        "field_name",
        "expected_event_type",
    ),
    [
        (
            "condition",
            ChangeEventType
            .PRICE_CONDITION_CHANGED,
        ),
        (
            "seller_id",
            ChangeEventType
            .PRICE_SELLER_CHANGED,
        ),
    ],
)
def test_create_price_context_events(
    field_name: str,
    expected_event_type: ChangeEventType,
) -> None:
    change = DetectedChange(
        change_type=ChangeType.PRICE,
        field_name=field_name,
        previous_value="old",
        current_value="new",
        direction=ChangeDirection.CHANGED,
    )

    event = create_change_events(
        make_change_set(change)
    )[0]

    assert event.event_type is expected_event_type


def test_create_inventory_out_of_stock_event() -> None:
    change = DetectedChange(
        change_type=ChangeType.INVENTORY,
        field_name="available",
        previous_value=True,
        current_value=False,
        direction=ChangeDirection.CHANGED,
    )

    event = create_change_events(
        make_change_set(change)
    )[0]

    assert (
        event.event_type
        is ChangeEventType.INVENTORY_OUT_OF_STOCK
    )
    assert event.is_inventory_event is True


def test_create_inventory_restocked_event() -> None:
    change = DetectedChange(
        change_type=ChangeType.INVENTORY,
        field_name="available",
        previous_value=False,
        current_value=True,
        direction=ChangeDirection.CHANGED,
    )

    event = create_change_events(
        make_change_set(change)
    )[0]

    assert (
        event.event_type
        is ChangeEventType.INVENTORY_RESTOCKED
    )


@pytest.mark.parametrize(
    (
        "direction",
        "absolute_change",
        "expected_event_type",
    ),
    [
        (
            ChangeDirection.INCREASED,
            Decimal("5"),
            ChangeEventType
            .INVENTORY_QUANTITY_INCREASED,
        ),
        (
            ChangeDirection.DECREASED,
            Decimal("-5"),
            ChangeEventType
            .INVENTORY_QUANTITY_DECREASED,
        ),
    ],
)
def test_create_inventory_quantity_event(
    direction: ChangeDirection,
    absolute_change: Decimal,
    expected_event_type: ChangeEventType,
) -> None:
    previous_value = (
        5
        if direction is ChangeDirection.INCREASED
        else 10
    )
    current_value = (
        10
        if direction is ChangeDirection.INCREASED
        else 5
    )

    change = DetectedChange(
        change_type=ChangeType.INVENTORY,
        field_name="quantity",
        previous_value=previous_value,
        current_value=current_value,
        direction=direction,
        absolute_change=absolute_change,
    )

    event = create_change_events(
        make_change_set(change)
    )[0]

    assert event.event_type is expected_event_type


def test_inventory_unknown_quantity_transition() -> None:
    change = DetectedChange(
        change_type=ChangeType.INVENTORY,
        field_name="quantity",
        previous_value=None,
        current_value=5,
        direction=ChangeDirection.CHANGED,
    )

    event = create_change_events(
        make_change_set(change)
    )[0]

    assert (
        event.event_type
        is ChangeEventType
        .INVENTORY_QUANTITY_CHANGED
    )


@pytest.mark.parametrize(
    (
        "field_name",
        "direction",
        "previous_value",
        "current_value",
        "expected_event_type",
    ),
    [
        (
            "seller_id",
            ChangeDirection.CHANGED,
            "seller_a",
            "seller_b",
            ChangeEventType.SELLER_CHANGED,
        ),
        (
            "seller_rating",
            ChangeDirection.INCREASED,
            4.0,
            4.5,
            ChangeEventType
            .SELLER_RATING_INCREASED,
        ),
        (
            "seller_rating",
            ChangeDirection.DECREASED,
            4.5,
            4.0,
            ChangeEventType
            .SELLER_RATING_DECREASED,
        ),
        (
            "seller_review_count",
            ChangeDirection.INCREASED,
            100,
            120,
            ChangeEventType
            .SELLER_REVIEW_COUNT_INCREASED,
        ),
        (
            "seller_review_count",
            ChangeDirection.DECREASED,
            120,
            100,
            ChangeEventType
            .SELLER_REVIEW_COUNT_DECREASED,
        ),
        (
            "seller_count",
            ChangeDirection.INCREASED,
            2,
            5,
            ChangeEventType
            .SELLER_COMPETITION_INCREASED,
        ),
        (
            "seller_count",
            ChangeDirection.DECREASED,
            5,
            2,
            ChangeEventType
            .SELLER_COMPETITION_DECREASED,
        ),
    ],
)
def test_create_seller_events(
    field_name: str,
    direction: ChangeDirection,
    previous_value: object,
    current_value: object,
    expected_event_type: ChangeEventType,
) -> None:
    absolute_change = None

    if direction is ChangeDirection.INCREASED:
        absolute_change = Decimal("1")

    if direction is ChangeDirection.DECREASED:
        absolute_change = Decimal("-1")

    change = DetectedChange(
        change_type=ChangeType.SELLER,
        field_name=field_name,
        previous_value=previous_value,
        current_value=current_value,
        direction=direction,
        absolute_change=absolute_change,
    )

    event = create_change_events(
        make_change_set(change)
    )[0]

    assert event.event_type is expected_event_type
    assert event.is_seller_event is True


def test_create_multiple_events_preserves_order() -> None:
    price_change = DetectedChange(
        change_type=ChangeType.PRICE,
        field_name="price",
        previous_value=100,
        current_value=90,
        direction=ChangeDirection.DECREASED,
        absolute_change=-10,
    )

    inventory_change = DetectedChange(
        change_type=ChangeType.INVENTORY,
        field_name="available",
        previous_value=True,
        current_value=False,
        direction=ChangeDirection.CHANGED,
    )

    events = create_change_events(
        make_change_set(
            price_change,
            inventory_change,
        )
    )

    assert len(events) == 2
    assert (
        events[0].event_type
        is ChangeEventType.PRICE_DROPPED
    )
    assert (
        events[1].event_type
        is ChangeEventType.INVENTORY_OUT_OF_STOCK
    )


def test_empty_change_set_creates_no_events() -> None:
    events = create_change_events(
        make_change_set()
    )

    assert events == ()


def test_create_change_events_rejects_invalid_input() -> None:
    with pytest.raises(
        TypeError,
        match="change_set은 ChangeSet이어야 합니다",
    ):
        create_change_events(
            "invalid"  # type: ignore[arg-type]
        )


def test_event_generates_unique_event_id() -> None:
    change = DetectedChange(
        change_type=ChangeType.PRICE,
        field_name="price",
        previous_value=100,
        current_value=90,
        direction=ChangeDirection.DECREASED,
        absolute_change=-10,
    )

    change_set = make_change_set(change)

    first = create_change_events(change_set)[0]
    second = create_change_events(change_set)[0]

    assert first.event_id
    assert second.event_id
    assert first.event_id != second.event_id


def test_event_metadata_is_immutable() -> None:
    event = ChangeDetectedEvent(
        event_type=ChangeEventType.PRICE_DROPPED,
        change_type=ChangeType.PRICE,
        direction=ChangeDirection.DECREASED,
        canonical_product_id="canonical_001",
        marketplace="ebay",
        previous_snapshot_id="previous",
        current_snapshot_id="current",
        field_name="price",
        previous_value=100,
        current_value=90,
        previous_observed_at=PREVIOUS_TIME,
        current_observed_at=CURRENT_TIME,
        metadata={"source": "test"},
    )

    assert isinstance(
        event.metadata,
        MappingProxyType,
    )

    with pytest.raises(TypeError):
        event.metadata["source"] = "changed"  # type: ignore[index]


def test_event_is_immutable() -> None:
    event = ChangeDetectedEvent(
        event_type=ChangeEventType.PRICE_DROPPED,
        change_type=ChangeType.PRICE,
        direction=ChangeDirection.DECREASED,
        canonical_product_id="canonical_001",
        marketplace="ebay",
        previous_snapshot_id="previous",
        current_snapshot_id="current",
        field_name="price",
        previous_value=100,
        current_value=90,
        previous_observed_at=PREVIOUS_TIME,
        current_observed_at=CURRENT_TIME,
    )

    with pytest.raises(FrozenInstanceError):
        event.field_name = "condition"  # type: ignore[misc]


def test_event_rejects_unchanged_direction() -> None:
    with pytest.raises(
        ValueError,
        match="UNCHANGED",
    ):
        ChangeDetectedEvent(
            event_type=(
                ChangeEventType.CHANGE_DETECTED
            ),
            change_type=ChangeType.PRICE,
            direction=ChangeDirection.UNCHANGED,
            canonical_product_id="canonical_001",
            marketplace="ebay",
            previous_snapshot_id="previous",
            current_snapshot_id="current",
            field_name="price",
            previous_value=100,
            current_value=100,
            previous_observed_at=PREVIOUS_TIME,
            current_observed_at=CURRENT_TIME,
        )


def test_publisher_protocols_support_runtime_check() -> None:
    class Publisher:
        def publish(
            self,
            event: ChangeDetectedEvent,
        ) -> None:
            pass

    class BatchPublisher:
        def publish_many(
            self,
            events: tuple[
                ChangeDetectedEvent,
                ...,
            ],
        ) -> None:
            pass

    assert isinstance(
        Publisher(),
        ChangeEventPublisher,
    )
    assert isinstance(
        BatchPublisher(),
        ChangeEventBatchPublisher,
    )