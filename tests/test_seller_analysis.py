from __future__ import annotations

from datetime import datetime, timezone

import pytest

from engine.seller_analysis import (
    analyze_seller,
)
from market_data.seller_snapshot import (
    SellerSnapshot,
)


def create_snapshot(
    *,
    seller_count: int = 1,
    seller_rating: float | None = 4.8,
    seller_review_count: int | None = 100,
    seller_id: str | None = "seller_001",
) -> SellerSnapshot:
    return SellerSnapshot(
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
        seller_id=seller_id,
        seller_rating=seller_rating,
        seller_review_count=seller_review_count,
        seller_count=seller_count,
        is_verified=True,
    )


def test_analyzes_low_competition():
    result = analyze_seller(
        create_snapshot(
            seller_count=1,
        )
    )

    assert result.competition_level == "낮음"
    assert result.risk_level == "낮음"


def test_analyzes_medium_competition():
    result = analyze_seller(
        create_snapshot(
            seller_count=3,
        )
    )

    assert result.competition_level == "보통"


def test_analyzes_high_competition():
    result = analyze_seller(
        create_snapshot(
            seller_count=10,
        )
    )

    assert result.competition_level == "높음"
    assert result.risk_level == "높음"


def test_analyzes_good_seller_quality():
    result = analyze_seller(
        create_snapshot(
            seller_rating=4.9,
        )
    )

    assert result.seller_quality == "양호"


def test_analyzes_risky_seller_quality():
    result = analyze_seller(
        create_snapshot(
            seller_rating=2.5,
        )
    )

    assert result.seller_quality == "위험"
    assert result.risk_level == "높음"


def test_handles_missing_seller_data():
    result = analyze_seller(
        None,
    )

    assert result.competition_level == "데이터 없음"
    assert result.risk_level == "높음"


def test_creates_summary():
    result = analyze_seller(
        create_snapshot()
    )

    assert "판매자 경쟁 수준은" in result.summary