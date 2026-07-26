from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from engine.price_snapshot_adapter import (
    price_snapshots_to_history_records,
)
from market_data.price_snapshot import PriceSnapshot


def create_snapshot(
    *,
    snapshot_id: str = "snapshot_001",
    item_id: str = "ITEM-001",
    price: Decimal = Decimal("99.99"),
    marketplace: str = "ebay",
) -> PriceSnapshot:
    return PriceSnapshot(
        snapshot_id=snapshot_id,
        canonical_product_id="product_001",
        marketplace=marketplace,
        observed_at=datetime(
            2026,
            7,
            26,
            tzinfo=timezone.utc,
        ),
        source_url="https://example.com/item",
        item_id=item_id,
        price=price,
        currency="USD",
        condition="New",
        seller_id="seller_001",
    )


def test_price_snapshots_to_history_records():
    snapshots = [
        create_snapshot()
    ]

    records = price_snapshots_to_history_records(
        snapshots,
        title="Test Product",
    )

    assert len(records) == 1

    record = records[0]

    assert record.marketplace == "ebay"
    assert record.item_id == "ITEM-001"
    assert record.title == "Test Product"
    assert record.price == Decimal("99.99")
    assert record.currency == "USD"
    assert record.condition == "New"
    assert record.seller_id == "seller_001"
    assert (
        record.canonical_product_id
        == "product_001"
    )


def test_price_is_preserved_as_decimal():
    snapshots = [
        create_snapshot(
            price=Decimal("120.50")
        )
    ]

    records = price_snapshots_to_history_records(
        snapshots,
        title="Product",
    )

    assert isinstance(
        records[0].price,
        Decimal,
    )

    assert records[0].price == Decimal(
        "120.50"
    )


def test_requires_title():
    snapshots = [
        create_snapshot()
    ]

    with pytest.raises(ValueError):
        price_snapshots_to_history_records(
            snapshots,
            title="",
        )


def test_rejects_empty_snapshots():
    with pytest.raises(ValueError):
        price_snapshots_to_history_records(
            [],
            title="Product",
        )


def test_rejects_invalid_snapshot_type():
    with pytest.raises(TypeError):
        price_snapshots_to_history_records(
            ["invalid"],
            title="Product",
        )