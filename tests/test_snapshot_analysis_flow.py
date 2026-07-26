from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from engine.price_snapshot_adapter import (
    price_snapshots_to_history_records,
)
from engine.price_trend import (
    analyze_price_trend,
)
from market_data.price_snapshot import (
    PriceSnapshot,
)


def create_snapshot(
    *,
    snapshot_id: str,
    price: str,
    day: int,
) -> PriceSnapshot:
    return PriceSnapshot(
        snapshot_id=snapshot_id,
        canonical_product_id="product_001",
        marketplace="ebay",
        observed_at=datetime(
            2026,
            7,
            day,
            tzinfo=timezone.utc,
        ),
        source_url="https://example.com/item",
        item_id="ITEM-001",
        price=Decimal(price),
        currency="USD",
        condition="New",
        seller_id="seller_001",
    )


def test_snapshot_to_price_trend_flow():
    snapshots = [
        create_snapshot(
            snapshot_id="snapshot_001",
            price="120.00",
            day=1,
        ),
        create_snapshot(
            snapshot_id="snapshot_002",
            price="100.00",
            day=10,
        ),
    ]

    records = price_snapshots_to_history_records(
        snapshots,
        title="Test Product",
    )

    trend = analyze_price_trend(
        records
    )

    assert trend.sample_size == 2
    assert trend.oldest_price == 120.0
    assert trend.current_price == 100.0
    assert trend.absolute_change == -20.0
    assert trend.trend_direction == "하락"
    assert trend.price_position == "기간 최저가"
    assert trend.recommendation == "매입 검토"


def test_snapshot_data_is_preserved():
    snapshots = [
        create_snapshot(
            snapshot_id="snapshot_001",
            price="99.99",
            day=1,
        )
    ]

    records = price_snapshots_to_history_records(
        snapshots,
        title="Product",
    )

    record = records[0]

    assert record.marketplace == "ebay"
    assert record.item_id == "ITEM-001"
    assert record.currency == "USD"
    assert record.condition == "New"
    assert record.seller_id == "seller_001"