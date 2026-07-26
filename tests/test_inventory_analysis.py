from __future__ import annotations

from datetime import datetime, timezone

import pytest

from engine.inventory_analysis import (
    analyze_inventory,
)
from market_data.inventory_snapshot import (
    InventorySnapshot,
)


def create_snapshot(
    *,
    available: bool = True,
    quantity: int | None = 20,
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


def test_analyzes_sufficient_inventory():
    result = analyze_inventory(
        create_snapshot(
            quantity=20,
        )
    )

    assert result.availability == "재고 있음"
    assert result.stock_level == "충분"
    assert result.risk_level == "낮음"
    assert result.can_purchase is True


def test_analyzes_low_inventory():
    result = analyze_inventory(
        create_snapshot(
            quantity=3,
        )
    )

    assert result.availability == "재고 있음"
    assert result.stock_level == "부족"
    assert result.risk_level == "중간"
    assert result.can_purchase is True


def test_analyzes_out_of_stock():
    result = analyze_inventory(
        create_snapshot(
            available=False,
            quantity=0,
        )
    )

    assert result.availability == "품절"
    assert result.risk_level == "높음"
    assert result.can_purchase is False


def test_analyzes_missing_inventory_data():
    result = analyze_inventory(
        None
    )

    assert result.availability == "데이터 없음"
    assert result.can_purchase is False
    assert result.risk_level == "높음"


def test_analyzes_unknown_quantity():
    result = analyze_inventory(
        create_snapshot(
            quantity=None,
        )
    )

    assert result.stock_level == "수량 미확인"
    assert result.risk_level == "낮음"


def test_summary_is_generated():
    result = analyze_inventory(
        create_snapshot()
    )

    assert "재고 상태는" in result.summary