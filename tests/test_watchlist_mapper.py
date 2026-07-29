from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.domain.watchlist import (
    WatchItem,
    WatchItemStatus,
)
from app.infrastructure.watchlist.mapper import (
    watch_item_from_row,
    watch_item_to_record,
)


BASE_TIME = datetime(
    2026,
    7,
    29,
    1,
    0,
    tzinfo=timezone.utc,
)


def make_watch_item() -> WatchItem:
    return WatchItem(
        watch_id="watch-1",
        marketplace="ebay",
        item_id="item-1",
        canonical_product_id=(
            "canonical-iphone-17-128"
        ),
        title="Apple iPhone 17 128GB",
        current_price=500.0,
        currency="USD",
        url="https://example.com/item-1",
        brand="Apple",
        model_number="A0001",
        target_roi=30.0,
        target_net_profit=100.0,
        note="가격 하락 감시",
        status=WatchItemStatus.WATCHING,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
        last_analyzed_at=None,
    )


def test_watch_item_to_record_contains_storage_fields() -> None:
    item = make_watch_item()

    record = watch_item_to_record(item)

    assert record["watch_id"] == "watch-1"
    assert record["identity_key"] == (
        "canonical:canonical-iphone-17-128"
    )
    assert record["marketplace"] == "ebay"
    assert record["item_id"] == "item-1"
    assert record["current_price"] == 500.0
    assert record["status"] == "watching"
    assert record["created_at"] == (
        BASE_TIME.isoformat()
    )
    assert record["last_analyzed_at"] is None


def test_watch_item_mapper_round_trip() -> None:
    original = make_watch_item()
    record = watch_item_to_record(original)

    restored = watch_item_from_row(record)

    assert restored.watch_id == original.watch_id
    assert restored.identity_key == (
        original.identity_key
    )
    assert (
        restored.canonical_product_id
        == original.canonical_product_id
    )
    assert restored.title == original.title
    assert (
        restored.current_price
        == original.current_price
    )
    assert restored.target_roi == 30.0
    assert restored.target_net_profit == 100.0
    assert (
        restored.status
        is WatchItemStatus.WATCHING
    )
    assert restored.created_at == BASE_TIME
    assert restored.updated_at == BASE_TIME
    assert restored.last_analyzed_at is None


def test_watch_item_mapper_preserves_analysis_time() -> None:
    analyzed_at = datetime(
        2026,
        7,
        30,
        1,
        0,
        tzinfo=timezone.utc,
    )
    item = make_watch_item()
    item.record_analysis(
        observed_price=450.0,
        analyzed_at=analyzed_at,
    )

    restored = watch_item_from_row(
        watch_item_to_record(item)
    )

    assert restored.current_price == 450.0
    assert restored.updated_at == analyzed_at
    assert (
        restored.last_analyzed_at
        == analyzed_at
    )


def test_watch_item_from_row_rejects_invalid_status() -> None:
    record = watch_item_to_record(
        make_watch_item()
    )
    record["status"] = "deleted"

    with pytest.raises(ValueError):
        watch_item_from_row(record)


def test_watch_item_from_row_rejects_naive_datetime() -> None:
    record = watch_item_to_record(
        make_watch_item()
    )
    record["created_at"] = (
        "2026-07-29T01:00:00"
    )

    with pytest.raises(
        ValueError,
        match="timezone-aware",
    ):
        watch_item_from_row(record)