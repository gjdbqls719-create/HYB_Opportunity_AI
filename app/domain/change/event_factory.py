from __future__ import annotations

from app.domain.change.events import (
    ChangeDetectedEvent,
    ChangeEventType,
)
from app.domain.change.models import (
    ChangeDirection,
    ChangeSet,
    ChangeType,
    DetectedChange,
)


def create_change_events(
    change_set: ChangeSet,
) -> tuple[ChangeDetectedEvent, ...]:
    """
    ChangeSet의 실제 변경 항목을 도메인 이벤트로 변환한다.

    변화가 없는 ChangeSet은 빈 tuple을 반환한다.
    하나의 DetectedChange는 하나의 이벤트가 된다.
    """
    if not isinstance(change_set, ChangeSet):
        raise TypeError(
            "change_set은 ChangeSet이어야 합니다."
        )

    events: list[ChangeDetectedEvent] = []

    for change in change_set.changes:
        if not change.has_changed:
            continue

        events.append(
            _create_event(
                change_set=change_set,
                change=change,
            )
        )

    return tuple(events)


def _create_event(
    *,
    change_set: ChangeSet,
    change: DetectedChange,
) -> ChangeDetectedEvent:
    return ChangeDetectedEvent(
        event_type=_resolve_event_type(change),
        change_type=change.change_type,
        direction=change.direction,
        canonical_product_id=(
            change_set.canonical_product_id
        ),
        marketplace=change_set.marketplace,
        previous_snapshot_id=(
            change_set.previous_snapshot_id
        ),
        current_snapshot_id=(
            change_set.current_snapshot_id
        ),
        field_name=change.field_name,
        previous_value=change.previous_value,
        current_value=change.current_value,
        previous_observed_at=(
            change_set.previous_observed_at
        ),
        current_observed_at=(
            change_set.current_observed_at
        ),
        absolute_change=change.absolute_change,
        percentage_change=(
            change.percentage_change
        ),
        metadata={
            "change_set_detected_at": (
                change_set.detected_at.isoformat()
            ),
        },
    )


def _resolve_event_type(
    change: DetectedChange,
) -> ChangeEventType:
    if change.change_type is ChangeType.PRICE:
        return _resolve_price_event_type(change)

    if (
        change.change_type
        is ChangeType.INVENTORY
    ):
        return _resolve_inventory_event_type(
            change
        )

    if change.change_type is ChangeType.SELLER:
        return _resolve_seller_event_type(change)

    return ChangeEventType.CHANGE_DETECTED


def _resolve_price_event_type(
    change: DetectedChange,
) -> ChangeEventType:
    if change.field_name == "price":
        if (
            change.direction
            is ChangeDirection.DECREASED
        ):
            return ChangeEventType.PRICE_DROPPED

        if (
            change.direction
            is ChangeDirection.INCREASED
        ):
            return (
                ChangeEventType.PRICE_INCREASED
            )

    if change.field_name == "condition":
        return (
            ChangeEventType
            .PRICE_CONDITION_CHANGED
        )

    if change.field_name == "seller_id":
        return (
            ChangeEventType.PRICE_SELLER_CHANGED
        )

    return ChangeEventType.CHANGE_DETECTED


def _resolve_inventory_event_type(
    change: DetectedChange,
) -> ChangeEventType:
    if change.field_name == "available":
        if (
            change.previous_value is True
            and change.current_value is False
        ):
            return (
                ChangeEventType
                .INVENTORY_OUT_OF_STOCK
            )

        if (
            change.previous_value is False
            and change.current_value is True
        ):
            return (
                ChangeEventType
                .INVENTORY_RESTOCKED
            )

    if change.field_name == "quantity":
        if (
            change.direction
            is ChangeDirection.INCREASED
        ):
            return (
                ChangeEventType
                .INVENTORY_QUANTITY_INCREASED
            )

        if (
            change.direction
            is ChangeDirection.DECREASED
        ):
            return (
                ChangeEventType
                .INVENTORY_QUANTITY_DECREASED
            )

        return (
            ChangeEventType
            .INVENTORY_QUANTITY_CHANGED
        )

    return ChangeEventType.CHANGE_DETECTED


def _resolve_seller_event_type(
    change: DetectedChange,
) -> ChangeEventType:
    if change.field_name == "seller_id":
        return ChangeEventType.SELLER_CHANGED

    if change.field_name == "seller_rating":
        if (
            change.direction
            is ChangeDirection.INCREASED
        ):
            return (
                ChangeEventType
                .SELLER_RATING_INCREASED
            )

        if (
            change.direction
            is ChangeDirection.DECREASED
        ):
            return (
                ChangeEventType
                .SELLER_RATING_DECREASED
            )

        return (
            ChangeEventType
            .SELLER_RATING_CHANGED
        )

    if (
        change.field_name
        == "seller_review_count"
    ):
        if (
            change.direction
            is ChangeDirection.INCREASED
        ):
            return (
                ChangeEventType
                .SELLER_REVIEW_COUNT_INCREASED
            )

        if (
            change.direction
            is ChangeDirection.DECREASED
        ):
            return (
                ChangeEventType
                .SELLER_REVIEW_COUNT_DECREASED
            )

        return (
            ChangeEventType
            .SELLER_REVIEW_COUNT_CHANGED
        )

    if change.field_name == "seller_count":
        if (
            change.direction
            is ChangeDirection.INCREASED
        ):
            return (
                ChangeEventType
                .SELLER_COMPETITION_INCREASED
            )

        if (
            change.direction
            is ChangeDirection.DECREASED
        ):
            return (
                ChangeEventType
                .SELLER_COMPETITION_DECREASED
            )

    return ChangeEventType.CHANGE_DETECTED