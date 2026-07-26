from __future__ import annotations

from datetime import datetime, timezone

import pytest

from market_data.inventory_snapshot import (
    InventorySnapshot,
)


def create_snapshot(
    *,
    available: bool = True,
    quantity: int | None = 10,
) -> InventorySnapshot:
    return InventorySnapshot(
        snapshot_id="snapshot_001",
        canonical_product_id="product_001",
        marketplace="ebay",
        observed_at=datetime(
            2026,
            7,
            26,
            tzinfo=timezone.utc,
        ),
        source_url="https://example.com/item",
        item_id="ITEM-001",
        available=available,
        quantity=quantity,
    )


def test_creates_available_inventory_snapshot():
    snapshot = create_snapshot()

    assert snapshot.item_id == "ITEM-001"
    assert snapshot.available is True
    assert snapshot.quantity == 10


def test_creates_out_of_stock_snapshot():
    snapshot = create_snapshot(
        available=False,
        quantity=0,
    )

    assert snapshot.available is False
    assert snapshot.quantity == 0


def test_rejects_empty_item_id():
    with pytest.raises(ValueError):
        InventorySnapshot(
            snapshot_id="snapshot_001",
            canonical_product_id="product_001",
            marketplace="ebay",
            observed_at=datetime(
                2026,
                7,
                26,
                tzinfo=timezone.utc,
            ),
            source_url="https://example.com/item",
            item_id="",
            available=True,
            quantity=1,
        )


def test_rejects_negative_quantity():
    with pytest.raises(ValueError):
        create_snapshot(
            quantity=-1,
        )


def test_rejects_available_with_zero_quantity():
    with pytest.raises(ValueError):
        create_snapshot(
            available=True,
            quantity=0,
        )


def test_snapshot_is_immutable():
    snapshot = create_snapshot()

    with pytest.raises(
        AttributeError
    ):
        snapshot.quantity = 20